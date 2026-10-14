"""Cliente de ejemplo para consumir los dos servicios HTTP de la practica."""

import requests


# Direcciones publicadas por Docker en el ordenador anfitrion.
USER_URL = "http://localhost:5050"
API_URL = "http://localhost:5051"


def authorization_header(token):
    """Construye la cabecera exigida por todos los endpoints autenticados."""
    return {"Authorization": f"Bearer {token}"}


def create_user(username, password, country):
    """Solicita al servicio de usuarios la creacion de una cuenta."""
    # requests convierte el diccionario de json a JSON y añade Content-Type.
    response = requests.put(
        f"{USER_URL}/user",
        json={
            "username": username,
            "password": password,
            "country": country,
        },
    )

    # El codigo HTTP permite distinguir el resultado sin inspeccionar el texto.
    if response.status_code == 400:
        print("Datos incompletos")
    elif response.status_code == 409:
        print("Usuario duplicado")
    elif response.status_code == 201:
        print("Usuario creado correctamente:")
        print(response.json())
    else:
        print("Respuesta inesperada")
        print(response.status_code)

    # Se devuelve Response para que otras comprobaciones puedan inspeccionarla.
    return response


def login(username, password):
    """Inicia sesion y devuelve la respuesta que contiene el token Bearer."""
    response = requests.post(
        f"{USER_URL}/user/login",
        json={
            "username": username,
            "password": password,
        },
    )

    if response.status_code == 400:
        print("Falta el usuario o la contraseña")
    elif response.status_code == 401:
        print("Credenciales invalidas")
    elif response.status_code == 200:
        print("Inicio de sesion correcto")
        print(response.json())
    else:
        print("Respuesta inesperada")
        print(response.status_code)

    return response


# Las funciones del servicio API (peliculas, carrito, votos y ventas) se añadiran
# a este archivo a medida que se implementen sus endpoints en api_service/api.py.
