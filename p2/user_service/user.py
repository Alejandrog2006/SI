import hashlib
import os
import uuid
import base64
import binascii
import hmac
from quart import Quart, request, jsonify
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TOKEN_SECRET = os.environ["TOKEN_SECRET"].encode()

app = Quart(__name__)
DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_async_engine(DATABASE_URL)

def generate_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token(user_id, session_version):
    payload = f"{user_id}:{session_version}"

    signature = hmac.new(
        TOKEN_SECRET,
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    token_data = f"{payload}:{signature}".encode()

    return base64.urlsafe_b64encode(token_data).decode()

def decode_token(token):
    try:
        token_data = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, session_version, signature = token_data.split(":")

        payload = f"{user_id}:{session_version}"

        expected_signature = hmac.new(
            TOKEN_SECRET,
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            return None

        return int(user_id), int(session_version)

    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None

def get_bearer_token():
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")

    if scheme != "Bearer" or not token:
        return None

    return token

@app.route('/user', methods=['PUT'])

async def create_user():
    data = await request.get_json()

    username = data.get("username")
    password = data.get("password")
    country = data.get("country")

    password_hash = generate_password(password)

    async with engine.begin() as connection:
        result = await connection.execute(
            text("""
                INSERT INTO users (username, password_hash, country)
                VALUES (:username, :password_hash, :country)
                ON CONFLICT (username) DO NOTHING
                RETURNING user_id
            """),
            {
                "username": username,
                "password_hash": password_hash,
                "country": country
            }
        )

    user = result.mappings().first()

    if user is None:
        return jsonify({"error": "El usuario ya existe"}), 409

    return jsonify({
        "message": "Usuario creado",
        "user_id": user["user_id"]
    }), 201


@app.route('/user/login', methods=['POST'])

async def login():
    data = await request.get_json()

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Faltan datos"}), 400

    async with engine.begin() as connection:
        result = await connection.execute(
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
                "password_hash": generate_password(password)
            }
        )

    user = result.mappings().first()

    if not user:
        return jsonify({"error": "Credenciales inválidas"}), 401

    token = generate_token(user["user_id"], user["session_version"])

    return jsonify({
        "user_id": user["user_id"],
        "username": user["username"],
        "session_version": user["session_version"],
        "money": user["money"],
        "role": user["role"]
    }), 200

@app.route('/user/logout', methods=['POST'])

async def logout():
     
    token = get_bearer_token()

    if token is None:
        return jsonify({"error": "Falta el token"}), 401

    token_data = decode_token(token)

    if token_data is None:
        return jsonify({"error": "Token inválido"}), 401

    user_id, session_version = token_data

    async with engine.begin() as connection:
        result = await connection.execute(
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
                "session_version": session_version
            }
        )

    user = result.mappings().first()

    if user is None:
        return jsonify({"error": "Token inválido o expirado"}), 401

    return jsonify({"message": "Sesión cerrada"}), 200

@app.route('/user/recharge', methods=['PATCH'])

async def recharge_balance():

    token = get_bearer_token()
    
    if token is None:
        return jsonify({"error": "Falta el token"}), 401
    
    token_data = decode_token(token)
    
    if token_data is None:
        return jsonify({"error": "Token inválido"}), 401

    async with engine.begin() as connection:
        result = await connection.execute(
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
                "session_version": session_version
            }
        )

    user = result.mappings().first()


@app.route('/user', methods=['DELETE'])

async def delete_user():

    async with engine.begin() as connection:
        result = await connection.execute(
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
                "session_version": session_version
            }
        )

    user = result.mappings().first()


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5050)