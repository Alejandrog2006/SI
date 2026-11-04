import os
import uuid
from quart import Quart, request, jsonify

app = Quart(__name__)

user_docs = {}  # Diccionario para almacenar los documentos de los usuarios [uid, documents[], public]

SECRET_UUID = uuid.UUID(os.environ["SECRET_UUID"])

def generate_token(user_uid):
    return str(uuid.uuid5(SECRET_UUID, user_uid))

def authenticate_user(uid, cripted_token):
    if not cripted_token or not uid:
        return False
    parts = cripted_token.split()
    if len(parts) != 2 or parts[0] != 'Bearer':
        return False

    return parts[1] == generate_token(uid)

@app.route('/file/<uid>', methods=['GET'])
async def list_docs(uid):

    token = request.headers.get('Authorization',"") # Si pasa la autentificacion los documentos son suyos

    if uid is None:
        return jsonify({"error": "Missing uid"}), 400

    if not authenticate_user(uid, token):
        return jsonify({"error": "Unauthorized"}), 401

    if uid in user_docs:
        user_data = user_docs[uid]
        return jsonify({"documents": user_data['documents']}), 200
    else:
        return jsonify({"error": "User not found"}), 404


@app.route('/file/<uid>/<filename>', methods=['PUT'])
async def modify_docs(uid,filename):

    data = await request.get_json()
    if not isinstance(data, dict):
      return jsonify({"error": "JSON object required"}), 400

    content = data.get("content")

    if not isinstance(content, str):
      return jsonify({"error": "Content is required"}), 400

    token = request.headers.get('Authorization',"")

    if uid is None or filename is None:
        return jsonify({"error": "Missing uid or filename"}), 400

    if not authenticate_user(uid, token):
        return jsonify({"error": "Unauthorized"}), 401

    if uid in user_docs:
        user_data = user_docs[uid]
        for i in range(len(user_data['documents'])):
            if user_data['documents'][i]['filename'] == filename:
                user_data['documents'][i]['content'] = content
                return jsonify({"message": "Document modified successfully"}), 200
        user_data['documents'].append({'filename': filename, 'content': content, 'public': False})
        return jsonify({"message": "Document modified successfully"}), 200
    else:
        user_docs[uid] = {'uid': uid, 'documents': [{'filename': filename,'content': content, 'public': False}]}
        return jsonify({"message": "Document modified successfully"}), 200

@app.route('/file/<uid>/<filename>', methods=['GET'])
async def restore_docs(uid,filename):

    token = request.headers.get('Authorization',"")
    if authenticate_user(uid, token) == False:
        authentification = False
    else:
        authentification = True

    if uid is None or filename is None:
        return jsonify({"error": "Missing uid or filename"}), 400

    if uid in user_docs:
        user_data = user_docs[uid]
        for doc in user_data['documents']:
            if doc['filename'] == filename and (doc['public'] == False) and  authentification == False:
                return jsonify({"error": "Access denied"}), 401
            elif doc['filename'] == filename:
                return jsonify({"document": doc}), 200
        return jsonify({"error": "Document not found"}), 404
    else:
        return jsonify({"error": "User not found"}), 404

@app.route('/file/<uid>/<filename>', methods=['DELETE'])
async def delete_docs(uid,filename):

    token = request.headers.get('Authorization',"")

    if not authenticate_user(uid, token):
        return jsonify({"error": "Unauthorized"}), 401

    if uid is None or filename is None:
        return jsonify({"error": "Missing uid or filename"}), 400

    if uid in user_docs:
        user_data = user_docs[uid]
        for i in range(len(user_data['documents'])):
            if user_data['documents'][i]['filename'] == filename:
                del user_data['documents'][i]
                return jsonify({"message": "Document deleted successfully"}), 200
        return jsonify({"error": "Document not found"}), 404
    else:
        return jsonify({"error": "User not found"}), 404

@app.route('/file/<uid>/<filename>', methods=['PATCH'])
async def visibility_docs(uid,filename):
    data = await request.get_json()
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400

    public = data.get("public")
    if not isinstance(public, bool):
        return jsonify({"error": "public must be True or False"}), 400

    token = request.headers.get('Authorization',"")

    if not authenticate_user(uid, token):
        return jsonify({"error": "Unauthorized"}), 401

    if uid in user_docs:
        user_data = user_docs[uid]
        for doc in user_data['documents']:
            if doc['filename'] == filename:
                doc['public'] = public
                return jsonify({"message": "Document visibility updated successfully"}), 200
        return jsonify({"error": "Document not found"}), 404
    else:
        return jsonify({"error": "User not found"}), 404

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5051)
