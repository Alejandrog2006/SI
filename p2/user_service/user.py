"""Servicio HTTP encargado de usuarios, sesiones y recargas de saldo."""

import base64
import binascii
import hashlib
import hmac
import os
from decimal import Decimal, InvalidOperation

from quart import Quart, jsonify, request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


# Quart usa este objeto para registrar y atender las rutas del servicio.
app = Quart(__name__)

# Docker proporciona la direccion de PostgreSQL y el secreto usado para firmar tokens.
# El mismo TOKEN_SECRET debe estar configurado en user_service y api_service.
DATABASE_URL = os.environ["DATABASE_URL"]
TOKEN_SECRET = os.environ["TOKEN_SECRET"].encode()

# El motor mantiene las conexiones asincronas con PostgreSQL. sessionmaker crea
# una sesion nueva para cada peticion y permite ejecutar SQL mediante await.
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


def generate_password(password):
    """Devuelve el hash SHA-256 que se guardara y comparara en PostgreSQL."""
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token(user_id, session_version):
    """Crea un token firmado que identifica al usuario y a su sesion actual."""
    # Estos son los datos que la API podra recuperar posteriormente del token.
    payload = f"{user_id}:{session_version}"

    # HMAC combina los datos con el secreto. Sin TOKEN_SECRET no se puede generar
    # una firma valida después de modificar el usuario o la version de sesion.
    signature = hmac.new(
        TOKEN_SECRET,
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    # El contenido final tiene el formato user_id:session_version:firma.
    token_data = f"{payload}:{signature}".encode()

    # Base64 permite enviar el token como texto dentro de una cabecera HTTP.
    return base64.urlsafe_b64encode(token_data).decode()


def decode_token(token):
    """Valida la firma y devuelve (user_id, session_version), o None si falla."""
    if not token:
        return None

    try:
        # Recupera y separa las tres partes que introdujo generate_token().
        token_data = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, session_version, signature = token_data.split(":")
        payload = f"{user_id}:{session_version}"

        # Calcula de nuevo la firma esperada sin confiar en la enviada por el cliente.
        expected_signature = hmac.new(
            TOKEN_SECRET,
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            return None

        return int(user_id), int(session_version)

    # Cualquier problema de formato convierte el token en invalido.
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None


def get_bearer_token():
    """Extrae el valor de la cabecera Authorization: Bearer <token>."""
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")

    if scheme != "Bearer" or not token:
        return None

    return token


@app.route("/user", methods=["PUT"])
async def create_user():
    """Crea un usuario activo con saldo cero y rol user."""
    # username, password y country llegan dentro del cuerpo JSON.
    data = await request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    country = data.get("country")

    if not username or not password or not country:
        return jsonify({"error": "Faltan datos"}), 400

    # PostgreSQL recibe el hash; nunca se almacena la contraseña original.
    password_hash = generate_password(password)

    async with async_session() as session:
        # session.begin confirma la transaccion al terminar o hace rollback si falla.
        async with session.begin():
            result = await session.execute(
                text("""
                    INSERT INTO users (username, password_hash, country)
                    VALUES (:username, :password_hash, :country)
                    ON CONFLICT (username) DO NOTHING
                    RETURNING user_id
                """),
                {
                    "username": username,
                    "password_hash": password_hash,
                    "country": country,
                },
            )
            # mappings() permite leer la columna devuelta por su nombre.
            user = result.mappings().first()

    # ON CONFLICT no devuelve una fila cuando el nombre ya esta registrado.
    if user is None:
        return jsonify({"error": "El usuario ya existe"}), 409

    return jsonify({
        "message": "Usuario creado",
        "user_id": user["user_id"],
    }), 201


@app.route("/user/login", methods=["POST"])
async def login():
    """Comprueba las credenciales y devuelve un token de sesion nuevo."""
    data = await request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Faltan datos"}), 400

    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    UPDATE users
                    SET session_version = session_version + 1
                    WHERE username = :username
                      AND password_hash = :password_hash
                      AND active = TRUE
                    RETURNING user_id, username, session_version, money, role
                """),
                {
                    "username": username,
                    "password_hash": generate_password(password),
                },
            )
            user = result.mappings().first()

    if user is None:
        return jsonify({"error": "Credenciales invalidas"}), 401

    # La version acaba de incrementarse, por lo que cada login produce otro token.
    token = generate_token(user["user_id"], user["session_version"])

    return jsonify({
        "user_id": user["user_id"],
        "username": user["username"],
        "token": token,
        "money": str(user["money"]),
        "role": user["role"],
    }), 200


@app.route("/user/logout", methods=["POST"])
async def logout():
    """Invalida el token actual incrementando la version de sesion."""
    token_data = decode_token(get_bearer_token())
    if token_data is None:
        return jsonify({"error": "Token invalido o ausente"}), 401

    user_id, session_version = token_data

    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    UPDATE users
                    SET session_version = session_version + 1
                    WHERE user_id = :user_id
                      AND session_version = :session_version
                      AND active = TRUE
                    RETURNING user_id
                """),
                {
                    "user_id": user_id,
                    "session_version": session_version,
                },
            )
            user = result.mappings().first()

    # Si no hay fila, el usuario cerro sesion antes o utilizo un token antiguo.
    if user is None:
        return jsonify({"error": "Token invalido o expirado"}), 401

    return jsonify({"message": "Sesion cerrada"}), 200


@app.route("/user/recharge", methods=["PATCH"])
async def recharge_balance():
    """Añade al saldo del usuario autenticado una cantidad monetaria positiva."""
    token_data = decode_token(get_bearer_token())
    if token_data is None:
        return jsonify({"error": "Token invalido o ausente"}), 401

    user_id, session_version = token_data
    data = await request.get_json(silent=True) or {}

    # Decimal evita los errores de precision que puede introducir float con dinero.
    try:
        amount = Decimal(str(data.get("amount")))
    except (InvalidOperation, TypeError):
        return jsonify({"error": "La cantidad no es valida"}), 400

    if not amount.is_finite() or amount <= 0:
        return jsonify({"error": "La cantidad debe ser positiva"}), 400

    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    UPDATE users
                    SET money = money + :amount
                    WHERE user_id = :user_id
                      AND session_version = :session_version
                      AND active = TRUE
                    RETURNING money
                """),
                {
                    "amount": amount,
                    "user_id": user_id,
                    "session_version": session_version,
                },
            )
            user = result.mappings().first()

    if user is None:
        return jsonify({"error": "Token invalido o expirado"}), 401

    return jsonify({
        "message": "Saldo recargado",
        "money": str(user["money"]),
    }), 200


@app.route("/user", methods=["DELETE"])
async def delete_user():
    """Desactiva al usuario autenticado sin borrar su historial de compras."""
    token_data = decode_token(get_bearer_token())
    if token_data is None:
        return jsonify({"error": "Token invalido o ausente"}), 401

    user_id, session_version = token_data

    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    UPDATE users
                    SET active = FALSE,
                        session_version = session_version + 1
                    WHERE user_id = :user_id
                      AND session_version = :session_version
                      AND active = TRUE
                    RETURNING user_id
                """),
                {
                    "user_id": user_id,
                    "session_version": session_version,
                },
            )
            user = result.mappings().first()

    if user is None:
        return jsonify({"error": "Token invalido o expirado"}), 401

    return jsonify({"message": "Usuario eliminado"}), 200


if __name__ == "__main__":
    # 0.0.0.0 permite que Docker publique el puerto 5050 fuera del contenedor.
    app.run(host="0.0.0.0", port=5050)
