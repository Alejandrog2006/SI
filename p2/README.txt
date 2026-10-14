PRÁCTICA 2 - VIDEOCLUB
======================

Estructura del proyecto
-----------------------

- database/schema.sql: tablas, restricciones, triggers y funciones almacenadas.
- database/populate.sql: datos iniciales para realizar pruebas.
- database/optimizacion.sql: comparación pendiente de la consulta de ventas.
- user_service/user.py: usuarios, autenticación, saldo y baja lógica.
- api_service/api.py: películas, carritos, pagos, votos y ventas.
- client/client.py: cliente HTTP y comprobaciones de los servicios.
- docker-compose.yml: PostgreSQL y los dos servicios Quart.

Ejecución
---------

Desde este directorio:

    docker-compose build
    docker-compose up -d
    docker-compose ps

Puertos publicados:

- PostgreSQL: localhost:9999
- Servicio de usuarios: http://localhost:5050
- API del videoclub: http://localhost:5051

La API del videoclub conserva respuestas 501 mientras se implementan sus
operaciones SQL. optimizacion.sql también sigue pendiente de completar.
