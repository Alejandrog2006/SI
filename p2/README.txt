PRÁCTICA 2 - VIDEOCLUB
======================

## Descripción

El proyecto implementa un videoclub mediante dos microservicios Quart:

- `user_service`: alta, login, logout, recarga de saldo y baja lógica.
- `api_service`: catálogo, películas, carritos, pagos, valoraciones e informe
  de ventas.

Ambos servicios comparten PostgreSQL y acceden a él exclusivamente mediante
SQLAlchemy Core asíncrono (`AsyncSession`, `text()`, `execute()` y `await`).
Las consultas son parametrizadas y cada operación de API utiliza un único
`execute()`. El token de sesión es stateless: se cifra con Fernet y se
invalida mediante `session_version`, sin almacenarlo en la base de datos.

## Estructura

- `database/schema.sql`: tablas, restricciones, funciones y triggers.
- `database/populate.sql`: datos ficticios iniciales.
- `database/optimizacion.sql`: EXPLAIN antes/después, índices y función
  optimizada del informe de ventas.
- `user_service/user.py`: API REST de usuarios.
- `api_service/api.py`: API REST del videoclub.
- `client/client.py`: cliente de pruebas funcionales y de errores.
- `docker-compose.yml`: PostgreSQL y los dos microservicios.
- `.env.example`: plantilla del secreto de sesión.

## Requisitos

- Docker y Docker Compose.
- Python 3.12 o superior para ejecutar el cliente fuera de Docker.
- `requests`, instalado desde `requirements.txt`.

## Configuración y ejecución

Desde esta carpeta:

    cp .env.example .env

Edita `.env` y establece un secreto largo y aleatorio. No subas `.env` al
repositorio; está excluido por `.gitignore`.

    docker-compose build
    docker-compose up -d
    docker-compose ps

La primera ejecución crea el esquema y carga los datos de prueba cuando el
volumen PostgreSQL está vacío. Los datos persisten en el volumen Docker
`p2_database_data`; por ello los scripts de inicialización no se vuelven a
ejecutar en reinicios normales.

Para reiniciar completamente la base de datos de desarrollo:

    docker-compose down -v
    docker-compose up -d --build

Puertos publicados:

- PostgreSQL: `localhost:9999`
- Servicio de usuarios: `http://localhost:5050`
- API principal: `http://localhost:5051`

## API disponible

### Usuarios (`user_service`)

- `PUT /user`: crea una cuenta.
- `POST /user/login`: devuelve un token Fernet.
- `POST /user/logout`: invalida el token actual.
- `PATCH /user/recharge`: recarga el saldo.
- `DELETE /user`: desactiva la cuenta autenticada.

### Videoclub (`api_service`)

- `POST /films`: crea una película como administrador.
- `DELETE /films/<film_id>`: desactiva una película.
- `GET /films`: filtra por título, año, director o actor.
- `POST /cart/films`: añade unidades al carrito y reserva stock.
- `POST /cart/pay`: paga el carrito y descuenta el saldo.
- `PUT /films/<film_id>/rating`: crea o modifica una valoración de 0 a 10.
- `GET /films/<film_id>/rating`: devuelve la valoración media.
- `GET /ventas/<year>/<country>`: devuelve ventas para administradores.

Las rutas protegidas requieren:

    Authorization: Bearer <token>

## Cliente de pruebas

Con los contenedores levantados, ejecuta:

    python -m pip install -r requirements.txt
    python client/client.py --examples

El cliente continúa aunque un caso falle y comprueba:

- alta duplicada, login incorrecto y campos inválidos;
- recarga válida, recarga negativa y uso sin token;
- filtros del catálogo y permisos de administrador;
- película inexistente, cantidad inválida, carrito y pago;
- valoración fuera de rango, modificación y consulta de media;
- informe de ventas como usuario y como administrador;
- logout, reutilización de token y baja lógica de usuario.

## Optimización

Ejecuta el script con `psql` después de iniciar PostgreSQL:

    docker exec -i si_p2_database psql -U alumnodb -d si1 \
      < database/optimizacion.sql

El script muestra el plan base con `EXPLAIN (ANALYZE, BUFFERS)`, crea:

- un índice parcial sobre compras pagadas y `paid_at`;
- un índice funcional sobre `LOWER(users.country)`;

y repite el plan usando un intervalo anual en vez de `EXTRACT(YEAR ...)`.
Finalmente reemplaza la función `sales_by_year_country()` para que
`/ventas/<year>/<country>` use la misma estrategia.

Los tiempos y planes exactos dependen del volumen y del estado de la caché.
La memoria debe incluir las salidas obtenidas y la discusión de la mejora.

## Preparación de la entrega

El ZIP debe contener el proyecto, incluyendo `memoria.pdf`, pero no debe
incluir entornos virtuales, cachés, bytecode ni metadatos del sistema:

    find . -type d \( -name __pycache__ -o -name .venv -o -name venv \) \
      -prune -exec rm -rf {} +
    find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
    zip -r P2.zip . -x '*.git/*' '*.env' '*.venv/*' '*__pycache__/*'

La memoria debe describir la arquitectura, las decisiones del modelo
relacional, el diagrama E-R, las pruebas del cliente y la comparación de
optimización.
