"""Aplicacion Quart del microservicio de biblioteca.

Autores: Manuel Salvador Mayor y Alejandro Gonzalez Garcia
"""

import json
from datetime import datetime
from pathlib import Path

from quart import Quart

from .mongodb_client import close_mongodb, init_mongodb
from .routes import library_bp


def _parse_datetime(value):
    """Convierte recursivamente las fechas ISO del poblado a datetime UTC."""
    if isinstance(value, list):
        return [_parse_datetime(item) for item in value]
    if isinstance(value, dict):
        return {key: _parse_datetime(item) for key, item in value.items()}
    if isinstance(value, str) and value.endswith("Z"):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return value


async def populate_database(collection) -> None:
    """Inserta el poblado oficial sin duplicar documentos en cada arranque."""
    populate_path = Path(__file__).with_name("populate.json")
    with populate_path.open(encoding="utf-8") as populate_file:
        books = json.load(populate_file)

    if not isinstance(books, list):
        raise ValueError("populate.json debe contener una lista de libros")

    for book in books:
        document = _parse_datetime(book)
        await collection.update_one(
            {"isbn": document["isbn"]},
            {"$setOnInsert": document},
            upsert=True,
        )


def create_app() -> Quart:
    """Crea la aplicacion y registra rutas y ciclo de vida de MongoDB."""
    application = Quart(__name__)
    application.register_blueprint(library_bp)

    @application.before_serving
    async def startup():
        collection = await init_mongodb()
        await populate_database(collection)

    @application.after_serving
    async def shutdown():
        await close_mongodb()

    return application


app = create_app()
