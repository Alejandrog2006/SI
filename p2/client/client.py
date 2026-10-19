"""Cliente HTTP y ejemplos de comprobacion para los servicios de la practica."""

import argparse
import time

import requests


# Puertos publicados por docker-compose en el ordenador anfitrion.
USER_URL = "http://localhost:5050"
API_URL = "http://localhost:5051"
REQUEST_TIMEOUT = 10


def authorization_header(token):
    """Construye la cabecera exigida por los endpoints autenticados."""
    return {"Authorization": f"Bearer {token}"}


def show_response(operation, response):
    """Muestra de forma uniforme el codigo y el JSON devuelto por un servicio."""
    print(f"\n{operation}: HTTP {response.status_code}")
    try:
        print(response.json())
    except requests.exceptions.JSONDecodeError:
        print(response.text)
    return response


def create_user(username, password, country):
    """Crea un usuario."""
    response = requests.put(
        f"{USER_URL}/user",
        json={
            "username": username,
            "password": password,
            "country": country,
        },
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Crear usuario", response)


def login(username, password):
    """Inicia sesion; el JSON correcto contiene el token Bearer."""
    response = requests.post(
        f"{USER_URL}/user/login",
        json={"username": username, "password": password},
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Login", response)


def logout(token):
    """Cierra la sesion e invalida el token enviado."""
    response = requests.post(
        f"{USER_URL}/user/logout",
        headers=authorization_header(token),
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Logout", response)


def recharge_balance(token, amount):
    """Recarga el saldo del usuario autenticado."""
    response = requests.patch(
        f"{USER_URL}/user/recharge",
        headers=authorization_header(token),
        json={"amount": amount},
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Recargar saldo", response)


def delete_user(token):
    """Desactiva al usuario propietario del token."""
    response = requests.delete(
        f"{USER_URL}/user",
        headers=authorization_header(token),
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Eliminar usuario", response)


def create_film(
    token,
    title,
    price,
    stock,
    release_year=None,
    director_id=None,
):
    """Crea una pelicula utilizando una sesion de administrador."""
    response = requests.post(
        f"{API_URL}/films",
        headers=authorization_header(token),
        json={
            "title": title,
            "release_year": release_year,
            "price": price,
            "stock": stock,
            "director_id": director_id,
        },
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Crear pelicula", response)


def delete_film(token, film_id):
    """Desactiva una pelicula utilizando una sesion de administrador."""
    response = requests.delete(
        f"{API_URL}/films/{film_id}",
        headers=authorization_header(token),
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Eliminar pelicula", response)


def list_films(title=None, year=None, director=None, actor=None):
    """Lista peliculas aplicando solamente los filtros indicados."""
    params = {
        key: value
        for key, value in {
            "title": title,
            "year": year,
            "director": director,
            "actor": actor,
        }.items()
        if value is not None
    }
    response = requests.get(
        f"{API_URL}/films",
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Listar peliculas", response)


def add_cart_film(token, film_id, quantity=1):
    """Añade unidades de una pelicula al carrito del usuario autenticado."""
    response = requests.post(
        f"{API_URL}/cart/films",
        headers=authorization_header(token),
        json={"film_id": film_id, "quantity": quantity},
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Añadir pelicula al carrito", response)


def pay_cart(token):
    """Paga en conjunto el contenido del carrito abierto."""
    response = requests.post(
        f"{API_URL}/cart/pay",
        headers=authorization_header(token),
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Pagar carrito", response)


def rate_film(token, film_id, rating):
    """Crea o modifica el voto del usuario para una pelicula."""
    response = requests.put(
        f"{API_URL}/films/{film_id}/rating",
        headers=authorization_header(token),
        json={"rating": rating},
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Votar pelicula", response)


def get_average_rating(film_id):
    """Consulta la puntuacion media de una pelicula."""
    response = requests.get(
        f"{API_URL}/films/{film_id}/rating",
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Consultar puntuacion media", response)


def get_sales(token, year, country):
    """Consulta como administrador las ventas del año y pais indicados."""
    response = requests.get(
        f"{API_URL}/ventas/{year}/{country}",
        headers=authorization_header(token),
        timeout=REQUEST_TIMEOUT,
    )
    return show_response("Consultar ventas", response)


def run_examples():
    """Ejecuta ejemplos correctos y erroneos de todos los recursos."""
    print("=== Errores de autenticacion y validacion ===")
    login("ana", "contraseña-incorrecta")
    list_films(year="año-invalido")

    user_login = login("ana", "ana1234")
    if user_login.status_code != 200:
        print("No se pueden continuar los ejemplos de usuario")
        return

    user_token = user_login.json()["token"]
    recharge_balance(user_token, -5)
    recharge_balance(user_token, 5)
    create_film(user_token, "Sin permisos", 1, 1)
    add_cart_film(user_token, 999999, 1)
    add_cart_film(user_token, 4, 1)
    rate_film(user_token, 1, 11)
    rate_film(user_token, 1, 8)
    get_average_rating(1)
    list_films(title="Origen")
    list_films(director="Nolan")
    list_films(actor="Cillian")
    pay_cart(user_token)
    get_sales(user_token, 2026, "Francia")
    logout(user_token)
    recharge_balance(user_token, 1)

    print("\n=== Operaciones de administrador ===")
    admin_login = login("admin", "admin1234")
    if admin_login.status_code == 200:
        admin_token = admin_login.json()["token"]
        created = create_film(
            admin_token,
            f"Pelicula de prueba {int(time.time())}",
            4.50,
            2,
            release_year=2026,
            director_id=1,
        )
        if created.status_code == 201:
            delete_film(admin_token, created.json()["film_id"])
        get_sales(admin_token, 2026, "Francia")
        logout(admin_token)

    print("\n=== Alta y baja de una cuenta temporal ===")
    username = f"cliente_prueba_{int(time.time())}"
    created_user = create_user(username, "prueba1234", "España")
    if created_user.status_code == 201:
        temporary_login = login(username, "prueba1234")
        if temporary_login.status_code == 200:
            delete_user(temporary_login.json()["token"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cliente de comprobacion de la practica 2"
    )
    parser.add_argument(
        "--examples",
        action="store_true",
        help="ejecuta ejemplos correctos y erroneos contra los contenedores",
    )
    arguments = parser.parse_args()

    if arguments.examples:
        try:
            run_examples()
        except requests.exceptions.RequestException as error:
            print(f"No se pudo contactar con los servicios: {error}")
    else:
        parser.print_help()
