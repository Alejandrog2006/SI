from quart import Quart
from .redis_client import close_redis, init_redis
from .routes import auth_bp


def create_app() -> Quart:
    """
    Factoría de la aplicación Quart del microservicio de autenticación.
    Registra las rutas y gestiona el ciclo de vida de la conexión con Redis.
    """
    application = Quart(__name__)

    # Registramos el Blueprint con los 4 endpoints (/auth/register, /auth/login, /auth/validate, /auth/logout)
    application.register_blueprint(auth_bp)

    @application.before_serving
    async def startup():
        """Se ejecuta automáticamente justo antes de que Hypercorn empiece a aceptar peticiones."""
        init_redis()

    @application.after_serving
    async def shutdown():
        """Se ejecuta automáticamente al detener el servidor para cerrar Redis limpiamente."""
        await close_redis()

    return application


# Instancia 'app' que Hypercorn ejecuta mediante: CMD ["hypercorn", "app:app", ...]
app = create_app()
