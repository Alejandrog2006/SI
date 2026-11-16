"""Cliente asincrono compartido por el servicio de biblioteca.

Autores: Manuel Salvador Mayor y Alejandro Gonzalez Garcia
"""

import os

from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection


mongo_client: AsyncMongoClient | None = None
books_collection: AsyncCollection | None = None


async def init_mongodb() -> AsyncCollection:
    """Abre la conexion, comprueba MongoDB y prepara la coleccion de libros."""
    global mongo_client, books_collection

    if mongo_client is None:
        mongo_url = os.getenv("MONGO_URL")
        if not mongo_url:
            host = os.getenv("MONGO_HOST", "mongodb")
            port = int(os.getenv("MONGO_PORT", "27017"))
            mongo_url = f"mongodb://{host}:{port}"

        database_name = os.getenv("MONGO_DATABASE", "library")
        mongo_client = AsyncMongoClient(mongo_url)
        await mongo_client.aconnect()
        await mongo_client.admin.command("ping")
        books_collection = mongo_client[database_name]["books"]
        await books_collection.create_index("isbn", unique=True)

    return books_collection


async def get_books_collection() -> AsyncCollection:
    """Devuelve la coleccion activa, inicializandola si fuese necesario."""
    if books_collection is None:
        return await init_mongodb()
    return books_collection


async def close_mongodb() -> None:
    """Cierra el cliente y libera su pool de conexiones."""
    global mongo_client, books_collection

    if mongo_client is not None:
        await mongo_client.close()
        mongo_client = None
        books_collection = None
