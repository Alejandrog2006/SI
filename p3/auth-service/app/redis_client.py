import os
# Importamos la versión asíncrona de redis-py para poder usar 'await' sin bloquear el servidor
import redis.asyncio as redis

# Variable global donde guardaremos la instancia única de conexión a Redis
redis_client: redis.Redis | None = None


def init_redis() -> redis.Redis:
    """Inicializa y devuelve el cliente asíncrono de Redis leyendo variables de entorno."""
    global redis_client
    if redis_client is None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            # decode_responses=True hace que Redis devuelva strings (str) en vez de bytes (b'...')
            redis_client = redis.from_url(redis_url, decode_responses=True)
        else:
            # Lee REDIS_HOST y REDIS_PORT definidos en el docker-compose.yml
            host = os.getenv("REDIS_HOST", "redis")
            port = int(os.getenv("REDIS_PORT", "6379"))
            db = int(os.getenv("REDIS_DB", "0"))
            redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True,
            )
    return redis_client


def get_redis() -> redis.Redis:
    """Devuelve el cliente activo de Redis (o lo inicializa si aún no existe)."""
    if redis_client is None:
        return init_redis()
    return redis_client


async def close_redis() -> None:
    """Cierra limpiamente el pool de conexiones con Redis cuando se apaga el contenedor."""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None
