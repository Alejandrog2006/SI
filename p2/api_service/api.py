"""API del catalogo, carrito, pagos, valoraciones e informe de ventas."""

import base64
import binascii
import hashlib
import hmac
import os
from decimal import Decimal, InvalidOperation

from quart import Quart, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
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
    """Lista peliculas activas por titulo, año, director o actor."""
    title = request.args.get("title")
    director = request.args.get("director")
    actor = request.args.get("actor")
    release_year = request.args.get("year")

    try:
        release_year = int(release_year) if release_year is not None else None
    except ValueError:
        return jsonify({"error": "El año debe ser un numero entero"}), 400

    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    SELECT
                        f.film_id,
                        f.title,
                        f.release_year,
                        f.price,
                        f.stock,
                        f.director_id,
                        d.name AS director,
                        average_film_rating(f.film_id) AS average_rating
                    FROM films AS f
                    LEFT JOIN directors AS d
                      ON d.director_id = f.director_id
                    WHERE f.active = TRUE
                      AND (
                          CAST(:title AS VARCHAR) IS NULL
                          OR LOWER(f.title) LIKE
                             LOWER('%' || CAST(:title AS VARCHAR) || '%')
                      )
                      AND (
                          CAST(:release_year AS INTEGER) IS NULL
                          OR f.release_year = CAST(:release_year AS INTEGER)
                      )
                      AND (
                          CAST(:director AS VARCHAR) IS NULL
                          OR LOWER(d.name) LIKE
                             LOWER('%' || CAST(:director AS VARCHAR) || '%')
                      )
                      AND (
                          CAST(:actor AS VARCHAR) IS NULL
                          OR EXISTS (
                              SELECT 1
                              FROM film_actors AS fa
                              JOIN actors AS a ON a.actor_id = fa.actor_id
                              WHERE fa.film_id = f.film_id
                                AND LOWER(a.name) LIKE
                                    LOWER('%' || CAST(:actor AS VARCHAR) || '%')
                          )
                      )
                    ORDER BY f.title, f.film_id
                """),
                {
                    "title": title,
                    "release_year": release_year,
                    "director": director,
                    "actor": actor,
                },
            )
            films = result.mappings().all()

    return jsonify({
        "films": [
            {
                "film_id": film["film_id"],
                "title": film["title"],
                "release_year": film["release_year"],
                "price": str(film["price"]),
                "stock": film["stock"],
                "director_id": film["director_id"],
                "director": film["director"],
                "average_rating": str(film["average_rating"]),
            }
            for film in films
        ]
    }), 200


@app.route("/cart/films", methods=["POST"])
async def add_cart_film():
    """Añade unidades de una pelicula al carrito abierto del usuario."""
    token_data = decode_token(get_bearer_token())
    if token_data is None:
        return jsonify({"error": "Token invalido o ausente"}), 401

    user_id, session_version = token_data
    data = await request.get_json(silent=True) or {}

    try:
        film_id = int(data.get("film_id"))
        quantity = int(data.get("quantity", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "film_id y quantity deben ser enteros"}), 400

    if quantity <= 0:
        return jsonify({"error": "quantity debe ser mayor que cero"}), 400

    try:
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(
                    text("""
                        WITH authenticated_user AS (
                            SELECT user_id
                            FROM users
                            WHERE user_id = :user_id
                              AND session_version = :session_version
                              AND active = TRUE
                        ),
                        selected_cart AS (
                            SELECT get_or_create_open_cart(user_id) AS cart_id
                            FROM authenticated_user
                        )
                        SELECT
                            cart_id,
                            add_film_to_cart(
                                cart_id,
                                :film_id,
                                :quantity
                            ) AS added
                        FROM selected_cart
                    """),
                    {
                        "user_id": user_id,
                        "session_version": session_version,
                        "film_id": film_id,
                        "quantity": quantity,
                    },
                )
                cart = result.mappings().first()
    except DBAPIError as error:
        return jsonify({
            "error": "No se pudo añadir la pelicula al carrito",
            "detail": str(error.orig).splitlines()[0],
        }), 409

    if cart is None:
        return jsonify({"error": "Token invalido o expirado"}), 401

    return jsonify({
        "message": "Pelicula añadida al carrito",
        "cart_id": cart["cart_id"],
        "film_id": film_id,
        "quantity_added": quantity,
    }), 200


@app.route("/cart/pay", methods=["POST"])
async def pay_cart():
    """Paga el carrito abierto y devuelve el total y la fecha de pago."""
    token_data = decode_token(get_bearer_token())
    if token_data is None:
        return jsonify({"error": "Token invalido o ausente"}), 401

    user_id, session_version = token_data

    try:
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(
                    text("""
                        WITH authenticated_user AS MATERIALIZED (
                            SELECT user_id
                            FROM users
                            WHERE user_id = :user_id
                              AND session_version = :session_version
                              AND active = TRUE
                        ),
                        open_cart AS (
                            SELECT c.cart_id
                            FROM carts AS c
                            JOIN authenticated_user AS u
                              ON u.user_id = c.user_id
                            WHERE c.status = 'open'
                        ),
                        payment AS (
                            SELECT p.*
                            FROM open_cart AS c
                            CROSS JOIN LATERAL pay_open_cart(c.cart_id) AS p
                        )
                        SELECT
                            EXISTS (
                                SELECT 1 FROM authenticated_user
                            ) AS authenticated,
                            payment.paid_cart_id,
                            payment.paid_total,
                            payment.payment_date
                        FROM (VALUES (1)) AS response(dummy)
                        LEFT JOIN payment ON TRUE
                    """),
                    {
                        "user_id": user_id,
                        "session_version": session_version,
                    },
                )
                payment = result.mappings().first()
    except DBAPIError as error:
        return jsonify({
            "error": "No se pudo pagar el carrito",
            "detail": str(error.orig).splitlines()[0],
        }), 409

    if not payment["authenticated"]:
        return jsonify({"error": "Token invalido o expirado"}), 401

    if payment["paid_cart_id"] is None:
        return jsonify({"error": "No existe un carrito abierto"}), 404

    return jsonify({
        "message": "Carrito pagado",
        "cart_id": payment["paid_cart_id"],
        "total": str(payment["paid_total"]),
        "paid_at": payment["payment_date"].isoformat(),
    }), 200


@app.route("/films/<int:film_id>/rating", methods=["PUT"])
async def rate_film(film_id):
    """Crea o modifica el voto del usuario autenticado."""
    token_data = decode_token(get_bearer_token())
    if token_data is None:
        return jsonify({"error": "Token invalido o ausente"}), 401

    user_id, session_version = token_data
    data = await request.get_json(silent=True) or {}

    try:
        rating_value = int(data.get("rating"))
    except (TypeError, ValueError):
        return jsonify({"error": "rating debe ser un numero entero"}), 400

    if not 0 <= rating_value <= 10:
        return jsonify({"error": "rating debe estar entre 0 y 10"}), 400

    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    WITH authenticated_user AS MATERIALIZED (
                        SELECT user_id
                        FROM users
                        WHERE user_id = :user_id
                          AND session_version = :session_version
                          AND active = TRUE
                    ),
                    selected_film AS MATERIALIZED (
                        SELECT film_id
                        FROM films
                        WHERE film_id = :film_id
                          AND active = TRUE
                    ),
                    saved_rating AS (
                        INSERT INTO ratings (user_id, film_id, rating)
                        SELECT u.user_id, f.film_id, :rating
                        FROM authenticated_user AS u
                        CROSS JOIN selected_film AS f
                        ON CONFLICT (user_id, film_id)
                        DO UPDATE SET
                            rating = EXCLUDED.rating,
                            created_at = CURRENT_TIMESTAMP
                        RETURNING user_id, film_id, rating, created_at
                    )
                    SELECT
                        EXISTS (
                            SELECT 1 FROM authenticated_user
                        ) AS authenticated,
                        EXISTS (
                            SELECT 1 FROM selected_film
                        ) AS film_exists,
                        saved_rating.user_id,
                        saved_rating.film_id,
                        saved_rating.rating,
                        saved_rating.created_at
                    FROM (VALUES (1)) AS response(dummy)
                    LEFT JOIN saved_rating ON TRUE
                """),
                {
                    "user_id": user_id,
                    "session_version": session_version,
                    "film_id": film_id,
                    "rating": rating_value,
                },
            )
            saved_rating = result.mappings().first()

    if not saved_rating["authenticated"]:
        return jsonify({"error": "Token invalido o expirado"}), 401

    if not saved_rating["film_exists"]:
        return jsonify({"error": "La pelicula no existe"}), 404

    return jsonify({
        "message": "Voto guardado",
        "user_id": saved_rating["user_id"],
        "film_id": saved_rating["film_id"],
        "rating": saved_rating["rating"],
        "created_at": saved_rating["created_at"].isoformat(),
    }), 200


@app.route("/films/<int:film_id>/rating", methods=["GET"])
async def get_average_rating(film_id):
    """Devuelve la puntuacion media de una pelicula activa."""
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    SELECT
                        film_id,
                        title,
                        average_film_rating(film_id) AS average_rating
                    FROM films
                    WHERE film_id = :film_id
                      AND active = TRUE
                """),
                {"film_id": film_id},
            )
            film = result.mappings().first()

    if film is None:
        return jsonify({"error": "La pelicula no existe"}), 404

    return jsonify({
        "film_id": film["film_id"],
        "title": film["title"],
        "average_rating": str(film["average_rating"]),
    }), 200


@app.route("/ventas/<int:year>/<country>", methods=["GET"])
async def get_sales(year, country):
    """Devuelve las ventas de un año y pais a un administrador autenticado."""
    token_data = decode_token(get_bearer_token())
    if token_data is None:
        return jsonify({"error": "Token invalido o ausente"}), 401

    user_id, session_version = token_data

    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                text("""
                    WITH authenticated_admin AS MATERIALIZED (
                        SELECT user_id
                        FROM users
                        WHERE user_id = :user_id
                          AND session_version = :session_version
                          AND active = TRUE
                          AND role = 'admin'
                    )
                    SELECT
                        EXISTS (
                            SELECT 1 FROM authenticated_admin
                        ) AS authorized,
                        COALESCE(
                            (
                                SELECT jsonb_agg(
                                    to_jsonb(sale)
                                    ORDER BY sale.paid_at, sale.cart_id, sale.film_id
                                )
                                FROM authenticated_admin AS admin
                                CROSS JOIN LATERAL sales_by_year_country(
                                    :year,
                                    :country
                                ) AS sale
                            ),
                            '[]'::jsonb
                        ) AS sales
                """),
                {
                    "user_id": user_id,
                    "session_version": session_version,
                    "year": year,
                    "country": country,
                },
            )
            sales_result = result.mappings().first()

    if not sales_result["authorized"]:
        return jsonify({"error": "Se requiere una sesion de administrador"}), 403

    return jsonify({
        "year": year,
        "country": country,
        "sales": sales_result["sales"],
    }), 200


if __name__ == "__main__":
    # 0.0.0.0 permite publicar el servicio fuera del contenedor.
    app.run(host="0.0.0.0", port=5051)
