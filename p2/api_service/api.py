"""API del catalogo, carrito, pagos, valoraciones e informe de ventas."""

import base64
import binascii
import hashlib
import hmac
import os
from decimal import Decimal, InvalidOperation

from quart import Quart, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# Aplicacion Quart que publica los endpoints del videoclub.
app = Quart(__name__)

# Ambos servicios comparten la base de datos y el secreto de firma de los tokens.
DATABASE_URL = os.environ["DATABASE_URL"]
TOKEN_SECRET = os.environ["TOKEN_SECRET"].encode()

# Motor y fabrica de sesiones asincronas para ejecutar SQL mediante await.
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# El PDF incluye Base, aunque las tablas se crean en schema.sql y no mediante ORM.
Base = declarative_base()


def decode_token(token):
    """Comprueba la firma y devuelve (user_id, session_version), o None."""
    if not token:
        return None

    try:
        # El contenido tiene el formato user_id:session_version:firma.
        token_data = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, session_version, signature = token_data.split(":")
        payload = f"{user_id}:{session_version}"

        # Recalcula la firma con el secreto que tambien utiliza user_service.
        expected_signature = hmac.new(
            TOKEN_SECRET,
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            return None

        return int(user_id), int(session_version)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None


def get_bearer_token():
    """Extrae el token de Authorization: Bearer <token>."""
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")

    if scheme != "Bearer" or not token:
        return None

    return token


@app.route("/films", methods=["POST"])
async def create_film():
    """Crea una pelicula si la sesion pertenece a un administrador."""
    token_data = decode_token(get_bearer_token())
    if token_data is None:
        return jsonify({"error": "Autenticacion requerida"}), 401

    user_id, session_version = token_data
    data = await request.get_json(silent=True) or {}

    # title, price y stock son obligatorios; año y director son opcionales.
    if any(field not in data for field in ("title", "price", "stock")):
        return jsonify({"error": "title, price y stock son obligatorios"}), 400

    try:
        title = str(data["title"]).strip()
        price = Decimal(str(data["price"]))
        stock = int(data["stock"])
        release_year = data.get("release_year")
        release_year = int(release_year) if release_year is not None else None
        director_id = data.get("director_id")
        director_id = int(director_id) if director_id is not None else None
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"error": "Los datos de la pelicula no son validos"}), 400

    if not title or not price.is_finite() or price < 0 or stock < 0:
        return jsonify({
            "error": "title no puede estar vacio; price y stock deben ser no negativos"
        }), 400

    if release_year is not None and not 1888 <= release_year <= 9999:
        return jsonify({"error": "El año de estreno no es valido"}), 400

    try:
        async with async_session() as session:
            async with session.begin():
                # INSERT ... SELECT autentica al administrador e inserta la pelicula
                # dentro de una sola sentencia y un unico execute().
                result = await session.execute(
                    text("""
                        INSERT INTO films (
                            title, release_year, price, stock, director_id
                        )
                        SELECT
                            :title, :release_year, :price, :stock, :director_id
                        FROM users
                        WHERE user_id = :user_id
                          AND session_version = :session_version
                          AND active = TRUE
                          AND role = 'admin'
                        RETURNING film_id, title, release_year, price, stock,
                                  director_id, active, created_at
                    """),
                    {
                        "title": title,
                        "release_year": release_year,
                        "price": price,
                        "stock": stock,
                        "director_id": director_id,
                        "user_id": user_id,
                        "session_version": session_version,
                    },
                )
                film = result.mappings().first()
    except IntegrityError:
        return jsonify({"error": "El director indicado no existe"}), 400

    # No se inserta ninguna fila cuando la sesion no es valida o no es de admin.
    if film is None:
        return jsonify({
            "error": "Se requiere una sesion valida de administrador"
        }), 403

    return jsonify({
        "film_id": film["film_id"],
        "title": film["title"],
        "release_year": film["release_year"],
        "price": str(film["price"]),
        "stock": film["stock"],
        "director_id": film["director_id"],
        "active": film["active"],
        "created_at": film["created_at"].isoformat(),
    }), 201


@app.route("/films/<int:film_id>", methods=["DELETE"])
async def delete_film(film_id):
    """Desactiva una pelicula si la sesion pertenece a un administrador."""
    token_data = decode_token(get_bearer_token())
    if token_data is None:
        return jsonify({"error": "Token invalido o ausente"}), 401

    user_id, session_version = token_data

    async with async_session() as session:
        async with session.begin():
            # El borrado logico conserva las peliculas incluidas en compras antiguas.
            result = await session.execute(
                text("""
                    UPDATE films
                    SET active = FALSE
                    WHERE film_id = :film_id
                      AND active = TRUE
                      AND EXISTS (
                          SELECT 1
                          FROM users
                          WHERE user_id = :user_id
                            AND session_version = :session_version
                            AND active = TRUE
                            AND role = 'admin'
                      )
                    RETURNING film_id
                """),
                {
                    "film_id": film_id,
                    "user_id": user_id,
                    "session_version": session_version,
                },
            )
            film = result.mappings().first()

    if film is None:
        return jsonify({
            "error": "Pelicula inexistente o sesion sin permisos"
        }), 404

    return jsonify({"message": "Pelicula eliminada"}), 200


@app.route("/films", methods=["GET"])
async def list_films():
    """Listara las peliculas que coincidan con los filtros de la URL."""
    return jsonify({"error": "Operacion no implementada"}), 501


@app.route("/cart/films", methods=["POST"])
async def add_cart_film():
    """Añadira una pelicula al carrito del usuario autenticado."""
    return jsonify({"error": "Operacion no implementada"}), 501


@app.route("/cart/pay", methods=["POST"])
async def pay_cart():
    """Pagara el carrito abierto y devolvera la fecha de pago."""
    return jsonify({"error": "Operacion no implementada"}), 501


@app.route("/films/<int:film_id>/rating", methods=["PUT"])
async def rate_film(film_id):
    """Guardara o modificara el voto del usuario autenticado."""
    return jsonify({"error": "Operacion no implementada"}), 501


@app.route("/films/<int:film_id>/rating", methods=["GET"])
async def get_average_rating(film_id):
    """Devolvera la puntuacion media de la pelicula."""
    return jsonify({"error": "Operacion no implementada"}), 501


@app.route("/ventas/<int:year>/<country>", methods=["GET"])
async def get_sales(year, country):
    """Devolvera las ventas del año y pais indicados."""
    return jsonify({"error": "Operacion no implementada"}), 501


if __name__ == "__main__":
    # 0.0.0.0 permite publicar el servicio fuera del contenedor.
    app.run(host="0.0.0.0", port=5051)
