"""Cliente de pruebas funcionales para los dos microservicios de la práctica.


    Autores: Manuel Salvador Mayor y Alejandro González García
"""

import argparse
import time
from typing import Any

import requests


# Los puertos son los publicados por docker-compose en el ordenador anfitrión.
USER_URL = "http://localhost:5050"
API_URL = "http://localhost:5051"
REQUEST_TIMEOUT = 10


def authorization_header(token: str) -> dict[str, str]:
    """Construye la cabecera Bearer usada por las operaciones protegidas."""
    return {"Authorization": f"Bearer {token}"}


def request_json(
    method: str,
    url: str,
    *,
    expected_status: int | None = None,
    **kwargs: Any,
) -> requests.Response | None:
    """Ejecuta una petición, muestra su respuesta y no detiene la batería."""
    for attempt in range(1, 6):
        try:
            response = requests.request(
                method,
                url,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
            break
        except requests.exceptions.RequestException as error:
            if attempt == 5:
                print(f"[ERROR DE RED] {method} {url}: {error}")
                return None
            time.sleep(1)

    try:
        body = response.json()
    except requests.exceptions.JSONDecodeError:
        body = response.text

    status_ok = expected_status is None or response.status_code == expected_status
    marker = "OK" if status_ok else "FALLO"
    print(f"[{marker}] {method} {url} -> HTTP {response.status_code}: {body}")
    if not status_ok:
        print(f"       Se esperaba HTTP {expected_status}")
    return response


def response_token(response: requests.Response | None) -> str | None:
    """Extrae un token de login solo si la respuesta tiene el formato esperado."""
    if response is None or response.status_code != 200:
        return None
    try:
        token = response.json()["token"]
    except (KeyError, TypeError, requests.exceptions.JSONDecodeError):
        return None
    return token if isinstance(token, str) and token else None


def create_user(username: str, password: str, country: str, expected_status: int = 201):
    """Comprueba el alta de un usuario."""
    return request_json(
        "PUT",
        f"{USER_URL}/user",
        expected_status=expected_status,
        json={"username": username, "password": password, "country": country},
    )


def login(username: str, password: str, expected_status: int = 200):
    """Comprueba el login y, cuando procede, obtiene un token cifrado."""
    return request_json(
        "POST",
        f"{USER_URL}/user/login",
        expected_status=expected_status,
        json={"username": username, "password": password},
    )


def logout(token: str, expected_status: int = 200):
    """Comprueba el logout y la invalidación del token."""
    return request_json(
        "POST",
        f"{USER_URL}/user/logout",
        expected_status=expected_status,
        headers=authorization_header(token),
    )


def recharge_balance(token: str, amount: Any, expected_status: int = 200):
    """Comprueba una recarga válida o un rechazo de validación."""
    return request_json(
        "PATCH",
        f"{USER_URL}/user/recharge",
        expected_status=expected_status,
        headers=authorization_header(token),
        json={"amount": amount},
    )


def delete_user(token: str, expected_status: int = 200):
    """Comprueba la baja lógica de la cuenta."""
    return request_json(
        "DELETE",
        f"{USER_URL}/user",
        expected_status=expected_status,
        headers=authorization_header(token),
    )


def create_film(
    token: str | None,
    title: str,
    price: Any,
    stock: int,
    *,
    release_year: int | None = None,
    director_id: int | None = None,
    expected_status: int = 201,
):
    """Comprueba la creación de una película y sus permisos de administrador."""
    return request_json(
        "POST",
        f"{API_URL}/films",
        expected_status=expected_status,
        headers=authorization_header(token) if token else {},
        json={
            "title": title,
            "price": price,
            "stock": stock,
            "release_year": release_year,
            "director_id": director_id,
        },
    )


def delete_film(token: str, film_id: int, expected_status: int = 200):
    """Comprueba el borrado lógico de una película."""
    return request_json(
        "DELETE",
        f"{API_URL}/films/{film_id}",
        expected_status=expected_status,
        headers=authorization_header(token),
    )


def list_films(expected_status: int = 200, **filters: Any):
    """Comprueba el listado y los filtros de título, año, director y actor."""
    return request_json(
        "GET",
        f"{API_URL}/films",
        expected_status=expected_status,
        params={key: value for key, value in filters.items() if value is not None},
    )


def add_cart_film(
    token: str,
    film_id: int,
    quantity: int = 1,
    expected_status: int = 200,
):
    """Comprueba la reserva de stock al añadir una línea al carrito."""
    return request_json(
        "POST",
        f"{API_URL}/cart/films",
        expected_status=expected_status,
        headers=authorization_header(token),
        json={"film_id": film_id, "quantity": quantity},
    )


def pay_cart(token: str, expected_status: int = 200):
    """Comprueba el pago conjunto y la fecha de pago."""
    return request_json(
        "POST",
        f"{API_URL}/cart/pay",
        expected_status=expected_status,
        headers=authorization_header(token),
    )


def rate_film(
    token: str,
    film_id: int,
    rating: Any,
    expected_status: int = 200,
):
    """Comprueba la creación o modificación de una valoración."""
    return request_json(
        "PUT",
        f"{API_URL}/films/{film_id}/rating",
        expected_status=expected_status,
        headers=authorization_header(token),
        json={"rating": rating},
    )


def get_average_rating(film_id: int, expected_status: int = 200):
    """Comprueba la consulta de la media de una película."""
    return request_json(
        "GET",
        f"{API_URL}/films/{film_id}/rating",
        expected_status=expected_status,
    )


def get_sales(token: str, year: int, country: str, expected_status: int = 200):
    """Comprueba el informe protegido de ventas por año y país."""
    return request_json(
        "GET",
        f"{API_URL}/ventas/{year}/{country}",
        expected_status=expected_status,
        headers=authorization_header(token),
    )


def run_examples() -> None:
    """Ejecuta casos correctos y errores esperados sin abortar la ejecución."""
    suffix = int(time.time())
    username = f"cliente_prueba_{suffix}"
    password = "prueba1234"

    print("=== Disponibilidad y validación de usuarios ===")
    create_user(username, password, "España")
    create_user(username, password, "España", expected_status=409)
    request_json(
        "PUT",
        f"{USER_URL}/user",
        expected_status=400,
        json={"username": "tipo_invalido", "password": 1234, "country": "España"},
    )
    login(username, "contraseña-incorrecta", expected_status=401)
    login(username, "", expected_status=400)
    anonymous_recharge = request_json(
        "PATCH",
        f"{USER_URL}/user/recharge",
        expected_status=401,
        json={"amount": 5},
    )
    del anonymous_recharge

    user_login = login(username, password)
    user_token = response_token(user_login)
    if user_token is None:
        print("[BLOQUEADO] No se pudo continuar sin un token de usuario.")
        return

    recharge_balance(user_token, -5, expected_status=400)
    recharge_balance(user_token, 5)

    print("\n=== Catálogo y permisos ===")
    list_films(year="año-invalido", expected_status=400)
    list_films(title="Origen")
    list_films(year=2010)
    list_films(director="Nolan")
    list_films(actor="Cillian")
    create_film(user_token, "Sin permisos", 1, 1, expected_status=403)
    create_film(None, "Sin token", 1, 1, expected_status=401)
    delete_film(user_token, 1, expected_status=403)

    print("\n=== Carrito, stock y pago ===")
    add_cart_film(user_token, 999999, expected_status=409)
    add_cart_film(user_token, 1, 0, expected_status=400)
    add_cart_film(user_token, 1, 1)
    pay_cart(user_token, expected_status=409)
    recharge_balance(user_token, 20)
    pay_cart(user_token)
    pay_cart(user_token, expected_status=404)

    print("\n=== Valoraciones ===")
    rate_film(user_token, 1, 11, expected_status=400)
    rate_film(user_token, 1, 8)
    rate_film(user_token, 1, 9)
    get_average_rating(1)
    get_average_rating(999999, expected_status=404)

    print("\n=== Ventas y permisos de administrador ===")
    get_sales(user_token, 2026, "Francia", expected_status=403)
    admin_login = login("admin", "admin1234")
    admin_token = response_token(admin_login)
    if admin_token is not None:
        created = create_film(
            admin_token,
            f"Película de prueba {suffix}",
            4.50,
            2,
            release_year=2026,
            director_id=1,
        )
        if created is not None and created.status_code == 201:
            film_id = created.json().get("film_id")
            if isinstance(film_id, int):
                list_films(title=f"Película de prueba {suffix}")
                delete_film(admin_token, film_id)
                get_average_rating(film_id, expected_status=404)
        get_sales(admin_token, 2026, "Francia")
        logout(admin_token)

    print("\n=== Invalidación y baja de usuario ===")
    logout(user_token)
    recharge_balance(user_token, 1, expected_status=401)

    temporary_login = login(username, password)
    temporary_token = response_token(temporary_login)
    if temporary_token is not None:
        delete_user(temporary_token)
        login(username, password, expected_status=401)


if __name__ == "__main__":
    # El modo explícito evita lanzar peticiones contra servicios no iniciados.
    parser = argparse.ArgumentParser(
        description="Cliente de comprobación de la práctica 2"
    )
    parser.add_argument(
        "--examples",
        action="store_true",
        help="ejecuta casos correctos y errores esperados",
    )
    arguments = parser.parse_args()

    if arguments.examples:
        run_examples()
    else:
        parser.print_help()
