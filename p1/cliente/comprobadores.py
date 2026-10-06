import sys
import uuid

import requests


USER_URL = "http://localhost:5050"
FILE_URL = "http://localhost:5051"
TIMEOUT = 5

correctas = 0
fallidas = 0


def authorization(token):
    return {"Authorization": f"Bearer {token}"}


def response_json(response):
    try:
        return response.json()
    except requests.JSONDecodeError:
        return None


def comprobar(nombre, response, expected_status, condition=True):
    global correctas, fallidas

    status_ok = response.status_code == expected_status
    passed = status_ok and condition

    if passed:
        correctas += 1
        print(f"[OK] {nombre}")
    else:
        fallidas += 1
        print(f"[FALLO] {nombre}")
        print(f"  Código esperado: {expected_status}")
        print(f"  Código recibido: {response.status_code}")
        print(f"  Respuesta: {response.text}")

    return passed


def enviar(method, url, **kwargs):
    try:
        return requests.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as error:
        print(f"No se pudo conectar con {url}: {error}")
        print("Arranca user_service y file_service antes de ejecutar este archivo.")
        sys.exit(1)


def comprobar_create_user(name, password):
    response = enviar(
        "PUT",
        f"{USER_URL}/user",
        json={"name": name, "password": password},
    )
    data = response_json(response)
    valid_data = (
        isinstance(data, dict)
        and isinstance(data.get("uid"), str)
        and isinstance(data.get("token"), str)
    )
    comprobar("Crear usuario", response, 201, valid_data)

    response = enviar(
        "PUT",
        f"{USER_URL}/user",
        json={"name": name, "password": password},
    )
    comprobar("Rechazar usuario duplicado", response, 409)

    response = enviar(
        "PUT",
        f"{USER_URL}/user",
        json={"name": name},
    )
    comprobar("Rechazar creación sin password", response, 400)

    response = enviar(
        "PUT",
        f"{USER_URL}/user",
        json={"password": password},
    )
    comprobar("Rechazar creación sin nombre", response, 400)

    response = enviar(
        "PUT",
        f"{USER_URL}/user",
        json={"name": name, "password": 1234},
    )
    comprobar("Rechazar password que no sea texto", response, 400)

    if not valid_data:
        return None, None

    return data["uid"], data["token"]


def comprobar_login(name, password, uid, token):
    response = enviar(
        "POST",
        f"{USER_URL}/user",
        json={"name": name, "password": password},
    )
    data = response_json(response)
    same_credentials = (
        isinstance(data, dict)
        and data.get("uid") == uid
        and data.get("token") == token
    )
    comprobar("Login correcto", response, 200, same_credentials)

    response = enviar(
        "POST",
        f"{USER_URL}/user",
        json={"name": name, "password": "incorrecta"},
    )
    comprobar("Rechazar contraseña incorrecta", response, 401)

    response = enviar(
        "POST",
        f"{USER_URL}/user",
        json={"name": name},
    )
    comprobar("Rechazar login sin password", response, 400)

    response = enviar(
        "POST",
        f"{USER_URL}/user",
        json={"password": password},
    )
    comprobar("Rechazar login sin nombre", response, 400)

    response = enviar("POST", f"{USER_URL}/user", json=[])
    comprobar("Rechazar login con JSON que no sea un objeto", response, 400)


def comprobar_modify_user(name, old_password, new_password, token):
    response = enviar(
        "PATCH",
        f"{USER_URL}/user",
        json={"password": new_password},
    )
    comprobar("Rechazar cambio de password sin token", response, 401)

    response = enviar(
        "PATCH",
        f"{USER_URL}/user",
        headers=authorization("token-invalido"),
        json={"password": new_password},
    )
    comprobar("Rechazar token inválido al cambiar password", response, 401)

    response = enviar(
        "PATCH",
        f"{USER_URL}/user",
        headers=authorization(token),
        json={},
    )
    comprobar("Rechazar cambio sin password", response, 400)

    response = enviar(
        "PATCH",
        f"{USER_URL}/user",
        headers=authorization(token),
        json=[],
    )
    comprobar("Rechazar cambio con JSON que no sea un objeto", response, 400)

    response = enviar(
        "PATCH",
        f"{USER_URL}/user",
        headers=authorization(token),
        json={"password": new_password},
    )
    comprobar("Cambiar password", response, 200)

    response = enviar(
        "POST",
        f"{USER_URL}/user",
        json={"name": name, "password": old_password},
    )
    comprobar("Rechazar password anterior", response, 401)

    response = enviar(
        "POST",
        f"{USER_URL}/user",
        json={"name": name, "password": new_password},
    )
    comprobar("Aceptar password nueva", response, 200)


def comprobar_create_or_update_document(uid, token, filename):
    url = f"{FILE_URL}/file/{uid}/{filename}"

    response = enviar(
        "PUT",
        url,
        json={"content": "Contenido inicial"},
    )
    comprobar("Rechazar creación de documento sin token", response, 401)

    response = enviar(
        "PUT",
        url,
        headers=authorization("token-invalido"),
        json={"content": "Contenido inicial"},
    )
    comprobar("Rechazar creación con token inválido", response, 401)

    response = enviar(
        "PUT",
        url,
        headers=authorization(token),
        json={},
    )
    comprobar("Rechazar documento sin contenido", response, 400)

    response = enviar(
        "PUT",
        url,
        headers=authorization(token),
        json={"content": 1234},
    )
    comprobar("Rechazar contenido que no sea texto", response, 400)

    response = enviar(
        "PUT",
        url,
        headers=authorization(token),
        json={"content": "Contenido inicial"},
    )
    comprobar("Crear documento privado", response, 200)

    response = enviar(
        "PUT",
        url,
        headers=authorization(token),
        json={"content": "Contenido actualizado"},
    )
    comprobar("Actualizar documento", response, 200)


def comprobar_list_documents(uid, owner_token, other_token, filename):
    url = f"{FILE_URL}/file/{uid}"

    response = enviar("GET", url)
    comprobar("Rechazar listado sin token", response, 401)

    response = enviar("GET", url, headers=authorization(other_token))
    comprobar("Rechazar listado de otro usuario", response, 401)

    response = enviar("GET", url, headers=authorization(owner_token))
    data = response_json(response)
    documents = data.get("documents", []) if isinstance(data, dict) else []
    contains_document = any(
        document.get("filename") == filename
        and document.get("content") == "Contenido actualizado"
        and document.get("public") is False
        for document in documents
        if isinstance(document, dict)
    )
    comprobar("Listar documentos propios", response, 200, contains_document)


def comprobar_get_document(uid, owner_token, other_token, filename):
    url = f"{FILE_URL}/file/{uid}/{filename}"

    response = enviar("GET", url)
    comprobar("Rechazar acceso anónimo a documento privado", response, 401)

    response = enviar("GET", url, headers=authorization(other_token))
    comprobar("Rechazar acceso de otro usuario a documento privado", response, 401)

    response = enviar("GET", url, headers=authorization(owner_token))
    data = response_json(response)
    document = data.get("document") if isinstance(data, dict) else None
    correct_content = (
        isinstance(document, dict)
        and document.get("content") == "Contenido actualizado"
    )
    comprobar("Obtener documento privado", response, 200, correct_content)


def comprobar_visibility(uid, owner_token, other_token, filename):
    url = f"{FILE_URL}/file/{uid}/{filename}"

    response = enviar(
        "PATCH",
        url,
        headers=authorization(owner_token),
        json={},
    )
    comprobar("Rechazar cambio sin campo public", response, 400)

    response = enviar(
        "PATCH",
        url,
        headers=authorization(owner_token),
        json=[],
    )
    comprobar("Rechazar visibilidad con JSON que no sea un objeto", response, 400)

    response = enviar(
        "PATCH",
        url,
        json={"public": True},
    )
    comprobar("Rechazar cambio de visibilidad sin token", response, 401)

    response = enviar(
        "PATCH",
        url,
        headers=authorization(owner_token),
        json={"public": "true"},
    )
    comprobar("Rechazar visibilidad que no sea booleana", response, 400)

    response = enviar(
        "PATCH",
        url,
        headers=authorization(owner_token),
        json={"public": 0},
    )
    comprobar("Rechazar cero como visibilidad", response, 400)

    response = enviar(
        "PATCH",
        url,
        headers=authorization(other_token),
        json={"public": True},
    )
    comprobar("Rechazar cambio de visibilidad por otro usuario", response, 401)

    response = enviar(
        "PATCH",
        url,
        headers=authorization(owner_token),
        json={"public": True},
    )
    comprobar("Hacer público el documento", response, 200)

    response = enviar("GET", url)
    data = response_json(response)
    document = data.get("document") if isinstance(data, dict) else None
    public_document = (
        isinstance(document, dict)
        and document.get("content") == "Contenido actualizado"
        and document.get("public") is True
    )
    comprobar("Obtener documento público sin token", response, 200, public_document)

    response = enviar(
        "PATCH",
        url,
        headers=authorization(owner_token),
        json={"public": False},
    )
    comprobar("Volver a hacer privado el documento", response, 200)

    response = enviar("GET", url)
    comprobar("Volver a impedir el acceso anónimo", response, 401)

    response = enviar("GET", url, headers=authorization(owner_token))
    comprobar("Mantener acceso del propietario", response, 200)


def comprobar_delete_document(uid, owner_token, other_token, filename):
    url = f"{FILE_URL}/file/{uid}/{filename}"

    response = enviar("DELETE", url, headers=authorization(other_token))
    comprobar("Rechazar borrado por otro usuario", response, 401)

    response = enviar("DELETE", url, headers=authorization(owner_token))
    comprobar("Eliminar documento como propietario", response, 200)

    response = enviar("GET", url)
    comprobar("Documento eliminado no encontrado", response, 404)

    response = enviar("DELETE", url, headers=authorization(owner_token))
    comprobar("Rechazar borrado de documento inexistente", response, 404)

    response = enviar(
        "GET",
        f"{FILE_URL}/file/{uid}",
        headers=authorization(owner_token),
    )
    data = response_json(response)
    documents = data.get("documents") if isinstance(data, dict) else None
    comprobar("Listado vacío después del borrado", response, 200, documents == [])


def main():
    suffix = uuid.uuid4().hex[:8]
    alice_name = f"alice_{suffix}"
    bob_name = f"bob_{suffix}"
    alice_password = "alice_password"

    alice_uid, alice_token = comprobar_create_user(alice_name, alice_password)
    if alice_uid is None:
        print("No se puede continuar sin crear el usuario principal.")
        return 1

    comprobar_login(alice_name, alice_password, alice_uid, alice_token)
    comprobar_modify_user(
        alice_name,
        alice_password,
        "alice_new_password",
        alice_token,
    )

    _, bob_token = comprobar_create_user(bob_name, "bob_password")
    if bob_token is None:
        print("No se pueden comprobar permisos de terceros sin crear a Bob.")
        return 1

    filename = "notas.txt"
    comprobar_create_or_update_document(alice_uid, alice_token, filename)
    comprobar_list_documents(alice_uid, alice_token, bob_token, filename)
    comprobar_get_document(alice_uid, alice_token, bob_token, filename)
    comprobar_visibility(alice_uid, alice_token, bob_token, filename)
    comprobar_delete_document(alice_uid, alice_token, bob_token, filename)

    print()
    print(f"Pruebas correctas: {correctas}")
    print(f"Pruebas fallidas: {fallidas}")
    return 1 if fallidas else 0


if __name__ == "__main__":
    sys.exit(main())
