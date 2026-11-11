import os
import secrets
from quart import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash
from .redis_client import get_redis

# Blueprint agrupa todos los endpoints de autenticación para registrarlos luego en __init__.py
auth_bp = Blueprint("auth", __name__)

# Tiempo de expiración (TTL) de las sesiones temporales: 5 minutos = 300 segundos
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "300"))


def _extract_bearer_token() -> str | None:
    """
    Función auxiliar que lee la cabecera HTTP 'Authorization: Bearer <token>'
    y devuelve únicamente el string del <token>, o None si no existe o tiene mal formato.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):].strip()
    return token if token else None


@auth_bp.route("/auth/register", methods=["POST"])
async def register():
    """
    Endpoint 1: POST /auth/register
    Registra un usuario de forma permanente en Redis bajo la clave HASH 'user:{username}'.
    No tiene TTL y persiste en disco gracias a la opción --appendonly yes (AOF) de Redis.
    """
    # Leemos el cuerpo JSON de la petición de forma asíncrona
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400

    username = data.get("username")
    password = data.get("password")
    email = data.get("email")

    # Validamos que los tres campos existan, sean strings y no estén vacíos
    if (
        not isinstance(username, str) or not username.strip()
        or not isinstance(password, str) or not password
        or not isinstance(email, str) or not email.strip()
    ):
        return jsonify({"error": "username, password and email are required"}), 400

    username = username.strip()
    email = email.strip()
    user_key = f"user:{username}"

    r = get_redis()
    # Comprobamos si ya existe la clave 'user:{username}' en Redis para evitar duplicados
    if await r.exists(user_key):
        return jsonify({"error": "User already exists"}), 409

    # Hasheamos la contraseña para no guardarla jamás en texto plano
    password_hash = generate_password_hash(password)

    # Guardamos en Redis una estructura tipo HASH bajo la clave 'user:{username}' sin TTL
    await r.hset(
        user_key,
        mapping={
            "username": username,
            "password_hash": password_hash,
            "email": email,
        },
    )

    return jsonify({"message": "User registered successfully", "username": username}), 201


@auth_bp.route("/auth/login", methods=["POST"])
async def login():
    """
    Endpoint 2: POST /auth/login
    Verifica las credenciales del usuario contra el HASH 'user:{username}' de Redis.
    Si son válidas, genera un token aleatorio y crea la clave 'session:{token}' con TTL de 5 min.
    """
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400

    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "username and password are required"}), 400

    username = username.strip()
    user_key = f"user:{username}"

    r = get_redis()
    # hgetall recupera todos los campos del HASH 'user:{username}' como un diccionario Python
    user_data = await r.hgetall(user_key)
    if not user_data or not check_password_hash(user_data.get("password_hash", ""), password):
        return jsonify({"error": "Invalid credentials"}), 401

    # Generamos un token opaco criptográficamente seguro
    token = secrets.token_urlsafe(32)
    session_key = f"session:{token}"

    # Guardamos 'session:{token}' -> username como STRING con expiración automática (ex=300s)
    await r.set(session_key, username, ex=SESSION_TTL_SECONDS)

    return jsonify({"token": token}), 200


@auth_bp.route("/auth/validate", methods=["GET"])
async def validate():
    """
    Endpoint 3: GET /auth/validate (Uso interno por auth_request de Nginx)
    Comprueba si 'session:{token}' existe en Redis.
    - Si existe: devuelve 200 OK y la cabecera 'X-User-Id' con el username para que Nginx la inyecte.
    - Si no existe o caducó: devuelve 401 Unauthorized y Nginx bloquea el paso a library-service.
    """
    token = _extract_bearer_token()
    if not token:
        return jsonify({"error": "Missing or invalid Authorization header"}), 401

    r = get_redis()
    # Consultamos en Redis a qué usuario pertenece el token
    username = await r.get(f"session:{token}")
    if not username:
        return jsonify({"error": "Invalid or expired token"}), 401

    # Devolvemos cuerpo JSON, código 200 y el diccionario de cabeceras con 'X-User-Id'
    return jsonify({"user_id": username}), 200, {"X-User-Id": username}


@auth_bp.route("/auth/logout", methods=["POST"])
async def logout():
    """
    Endpoint 4: POST /auth/logout
    Invalida el token inmediatamente borrando la clave 'session:{token}' en Redis
    sin esperar a que se agote su TTL de 5 minutos.
    """
    token = _extract_bearer_token()
    if not token:
        return jsonify({"error": "Missing or invalid Authorization header"}), 401

    r = get_redis()
    # delete() devuelve el número de claves borradas (1 si existía, 0 si no existía/caducó/ya cerró sesión)
    deleted_count = await r.delete(f"session:{token}")
    if deleted_count == 0:
        return jsonify({"error": "Invalid, expired or already logged out token"}), 401

    return jsonify({"message": "Logged out successfully"}), 200
