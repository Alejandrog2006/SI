import hashlib
import os
import uuid
from quart import Quart, request, jsonify

app = Quart(__name__)

user_data = {}  # Diccionario para almacenar los datos de los usuarios

def generate_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token(user_uid):
    return str(uuid.uuid5(SECRET_UUID, user_uid))

SECRET_UUID = uuid.UUID(os.environ["SECRET_UUID"])

@app.route('/user', methods=['PUT'])

async def create_user():
    data = await request.get_json()
    if not isinstance(data, dict):
        return jsonify({'error': 'JSON object required'}), 400

    name = data.get('name')
    password = data.get('password')
    if not isinstance(name, str) or not name or not isinstance(password, str) or not password:
        return jsonify({'error': 'Name and password are required'}), 400

    if name in user_data:
        return jsonify({'error': 'User already exists'}), 409
    
    uid_del_usuario_como_string = str(uuid.uuid4()) # Este se habrá generado al hacer create_user 
    token = generate_token(uid_del_usuario_como_string)

    user_data[name] = {'uid': uid_del_usuario_como_string, 'password_hash': generate_password(password),}
    return jsonify({
        'message': 'User created successfully',
        'uid': str(uid_del_usuario_como_string),
        'token': str(token),
    }), 201

@app.route('/user', methods=['POST'])

async def login():
    data = await request.get_json()
    if not isinstance(data, dict):
        return jsonify({'error': 'JSON object required'}), 400

    name = data.get('name')
    password = data.get('password')
    if not isinstance(name, str) or not name or not isinstance(password, str) or not password:
        return jsonify({'error': 'Name and password are required'}), 400

    if not name in user_data or user_data[name]['password_hash'] != generate_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401

    token = generate_token(user_data[name]['uid'])
    return jsonify({
        'message': 'Login successful',
        'uid': str(user_data[name]['uid']),
        'token': str(token),
    }), 200

@app.route('/user', methods=['PATCH'])

async def modify_user():
    autorization = request.headers.get('Authorization', '')
    parts = autorization.split()

    if len(parts) != 2 or parts[0] != 'Bearer':
        return jsonify({'error': 'Invalid authorization header'}), 401

    for user in user_data.values():
        token_esperado = generate_token(user['uid'])
        if token_esperado == parts[1]:
            authenticated_user = user
            break
    else:
        return jsonify({'error': 'Invalid token'}), 401

    data = await request.get_json()
    if not isinstance(data, dict):
        return jsonify({'error': 'JSON object required'}), 400

    password = data.get('password')
    if not isinstance(password, str) or not password:
        return jsonify({'error': 'Password is required'}), 400

    authenticated_user['password_hash'] = generate_password(password)

    return jsonify({'message': 'Password updated successfully'}), 200

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5050)
