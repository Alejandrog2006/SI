"""Endpoints de catalogo y prestamos de la biblioteca.

Autores: Manuel Salvador Mayor y Alejandro Gonzalez Garcia
"""

from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from quart import Blueprint, jsonify, request

from .mongodb_client import get_books_collection


library_bp = Blueprint("library", __name__)

BOOK_FIELDS = (
    "isbn",
    "title",
    "author",
    "year",
    "publisher",
    "available_stock",
)


def _get_user_id() -> str | None:
    """Obtiene exclusivamente la identidad validada e inyectada por Nginx."""
    user_id = request.headers.get("X-User-Id", "").strip()
    return user_id or None


async def _get_json_object():
    """Devuelve el cuerpo JSON si es un objeto."""
    data = await request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _serialize_value(value):
    """Convierte tipos BSON y fechas a valores serializables como JSON."""
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _serialize_value(item)
            for key, item in value.items()
            if key != "_id"
        }
    return value


def _serialize_book(book):
    return _serialize_value(book)


def _validate_book(data):
    """Normaliza un libro o devuelve un mensaje de error."""
    if data is None:
        return None, "El cuerpo debe ser un objeto JSON"
    if any(field not in data for field in BOOK_FIELDS):
        return None, "Faltan campos obligatorios del libro"

    isbn = data["isbn"]
    title = data["title"]
    author = data["author"]
    year = data["year"]
    publisher = data["publisher"]
    stock = data["available_stock"]

    if not all(isinstance(value, str) for value in (isbn, title, author, publisher)):
        return None, "isbn, title, author y publisher deben ser texto"
    if isinstance(year, bool) or not isinstance(year, int):
        return None, "year debe ser un entero"
    if isinstance(stock, bool) or not isinstance(stock, int):
        return None, "available_stock debe ser un entero"

    isbn = isbn.strip()
    title = title.strip()
    author = author.strip()
    publisher = publisher.strip()
    if not all((isbn, title, author, publisher)):
        return None, "Los campos de texto no pueden estar vacios"
    if not 0 <= year <= 9999:
        return None, "year esta fuera del intervalo permitido"
    if stock < 0:
        return None, "available_stock no puede ser negativo"

    return {
        "isbn": isbn,
        "title": title,
        "author": author,
        "year": year,
        "publisher": publisher,
        "available_stock": stock,
        "loan_history": [],
    }, None


@library_bp.before_request
async def require_gateway_identity():
    """Rechaza llamadas que no contienen la identidad validada por el gateway."""
    if _get_user_id() is None:
        return jsonify({"error": "Autenticacion requerida"}), 401
    return None


@library_bp.route("/library/books", methods=["POST"])
async def create_book():
    """Crea un libro nuevo con un historial de prestamos vacio."""
    document, error = _validate_book(await _get_json_object())
    if error:
        return jsonify({"error": error}), 400

    collection = await get_books_collection()
    try:
        await collection.insert_one(document)
    except DuplicateKeyError:
        return jsonify({"error": "El libro ya existe"}), 409
    except PyMongoError:
        return jsonify({"error": "No se pudo crear el libro"}), 503

    return jsonify(_serialize_book(document)), 201


@library_bp.route("/library/books/out-of-stock", methods=["GET"])
async def list_out_of_stock_books():
    """Lista todos los libros que no tienen unidades disponibles."""
    collection = await get_books_collection()
    books = []
    async for book in collection.find({"available_stock": 0}):
        books.append(_serialize_book(book))
    return jsonify(books), 200


@library_bp.route("/library/books/<string:isbn>", methods=["GET"])
async def get_book(isbn):
    """Devuelve los datos y el historial completo de un libro."""
    collection = await get_books_collection()
    book = await collection.find_one({"isbn": isbn})
    if book is None:
        return jsonify({"error": "El libro no existe"}), 404
    return jsonify(_serialize_book(book)), 200


@library_bp.route("/library/books/<string:isbn>", methods=["DELETE"])
async def delete_book(isbn):
    """Borra un libro solamente cuando no tiene prestamos activos."""
    collection = await get_books_collection()
    deleted_book = await collection.find_one_and_delete({
        "isbn": isbn,
        "loan_history": {
            "$not": {"$elemMatch": {"return_date": None}},
        },
    })
    if deleted_book is not None:
        return jsonify({"message": "Libro eliminado"}), 200

    existing_book = await collection.find_one({"isbn": isbn}, {"_id": 1})
    if existing_book is None:
        return jsonify({"error": "El libro no existe"}), 404
    return jsonify({"error": "El libro tiene prestamos activos"}), 409


@library_bp.route("/library/loans/active", methods=["GET"])
async def list_active_loans():
    """Lista los libros prestados actualmente al usuario autenticado."""
    user_id = _get_user_id()
    collection = await get_books_collection()
    books = []
    query = {
        "loan_history": {
            "$elemMatch": {"user_id": user_id, "return_date": None},
        },
    }
    async for book in collection.find(query):
        book["loan_history"] = [
            loan for loan in book.get("loan_history", [])
            if loan.get("user_id") == user_id and loan.get("return_date") is None
        ]
        books.append(_serialize_book(book))
    return jsonify(books), 200


@library_bp.route("/library/loans/history", methods=["GET"])
async def list_loan_history():
    """Lista exclusivamente el historial del usuario autenticado."""
    user_id = _get_user_id()
    collection = await get_books_collection()
    books = []
    async for book in collection.find({"loan_history.user_id": user_id}):
        book["loan_history"] = [
            loan for loan in book.get("loan_history", [])
            if loan.get("user_id") == user_id
        ]
        books.append(_serialize_book(book))
    return jsonify(books), 200


@library_bp.route("/library/books/<string:isbn>/borrow", methods=["POST"])
async def borrow_book(isbn):
    """Presta una unidad mediante una unica operacion atomica de MongoDB."""
    user_id = _get_user_id()
    now = datetime.now(timezone.utc)
    collection = await get_books_collection()

    book = await collection.find_one_and_update(
        {
            "isbn": isbn,
            "available_stock": {"$gt": 0},
            "loan_history": {
                "$not": {
                    "$elemMatch": {
                        "user_id": user_id,
                        "return_date": None,
                    },
                },
            },
        },
        {
            "$inc": {"available_stock": -1},
            "$push": {
                "loan_history": {
                    "user_id": user_id,
                    "loan_date": now,
                    "return_date": None,
                },
            },
        },
        return_document=ReturnDocument.AFTER,
    )
    if book is not None:
        return jsonify(_serialize_book(book)), 200

    current = await collection.find_one(
        {"isbn": isbn},
        {"available_stock": 1, "loan_history": 1},
    )
    if current is None:
        return jsonify({"error": "El libro no existe"}), 404
    if any(
        loan.get("user_id") == user_id and loan.get("return_date") is None
        for loan in current.get("loan_history", [])
    ):
        return jsonify({"error": "El usuario ya tiene este libro prestado"}), 409
    return jsonify({"error": "No hay stock disponible"}), 409


@library_bp.route("/library/books/<string:isbn>/return", methods=["POST"])
async def return_book(isbn):
    """Cierra el prestamo activo y repone el stock de forma atomica."""
    user_id = _get_user_id()
    now = datetime.now(timezone.utc)
    collection = await get_books_collection()

    book = await collection.find_one_and_update(
        {
            "isbn": isbn,
            "loan_history": {
                "$elemMatch": {
                    "user_id": user_id,
                    "return_date": None,
                },
            },
        },
        {
            "$inc": {"available_stock": 1},
            "$set": {"loan_history.$.return_date": now},
        },
        return_document=ReturnDocument.AFTER,
    )
    if book is not None:
        return jsonify(_serialize_book(book)), 200

    existing_book = await collection.find_one({"isbn": isbn}, {"_id": 1})
    if existing_book is None:
        return jsonify({"error": "El libro no existe"}), 404
    return jsonify({"error": "El usuario no tiene un prestamo activo"}), 409
