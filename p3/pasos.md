# Esquema de trabajo de la Práctica 3

Este documento resume un orden de implementación y comprobación para la práctica. La estructura y los nombres de los elementos especificados en el enunciado deben conservarse, ya que los tests proporcionados dependerán de ellos.

## 1. Incorporar los archivos proporcionados

- Copiar el contenido oficial de `library-service/app/populate.json`.
- Copiar la batería oficial en `p3_test.py`.
- Copiar las dependencias oficiales en `p3_test_requirements.txt`.
- Configurar `pytest.ini` con la configuración entregada por la asignatura.
- No modificar los tests para adaptar la implementación.

## 2. Preparar el despliegue completo

Completar `docker-compose.yml` con cinco servicios:

1. `api-gateway`, basado en Nginx y único servicio accesible desde el exterior en el puerto 8080.
2. `auth-service`, accesible únicamente desde la red interna en el puerto 5050.
3. `library-service`, accesible únicamente desde la red interna en el puerto 5051.
4. Redis, con persistencia AOF habilitada mediante `--appendonly yes`.
5. MongoDB, con un volumen persistente.

Usar variables de entorno para hosts, puertos, base de datos y demás configuración que pueda cambiar. Añadir comprobaciones de salud y dependencias de arranque si son necesarias. No publicar al host los puertos internos de Redis, MongoDB ni los microservicios.

## 3. Configurar el API Gateway

Completar `api-gateway/nginx.conf` para:

- Enviar `/auth/*` a `auth-service:5050`.
- Proteger `/library/*` mediante `auth_request` contra `/auth/validate`.
- Rechazar la petición con `401` cuando falle la validación.
- Recoger `X-User-Id` de la respuesta de validación.
- Eliminar cualquier `X-User-Id` enviado por el cliente e inyectar el valor validado antes de reenviar la petición a `library-service:5051`.

Comprobar que los dos microservicios no sean accesibles directamente desde el equipo anfitrión.

## 4. Implementar el microservicio de autenticación

### 4.1 Cliente Redis

En `auth-service/app/redis_client.py`:

- Crear el cliente asíncrono con `redis.asyncio`.
- Tomar la URL o los parámetros de conexión del entorno.
- Preparar el cierre correcto de la conexión.

### 4.2 Aplicación Quart

En `auth-service/app/__init__.py`:

- Crear y configurar la aplicación Quart.
- Registrar las rutas del servicio.
- Gestionar la apertura y cierre de recursos durante el ciclo de vida.

### 4.3 Rutas

En `auth-service/app/routes.py`, implementar:

| Método | Ruta | Trabajo principal |
| --- | --- | --- |
| `POST` | `/auth/register` | Validar `username`, `password` y `email`; guardar un HASH `user:{username}` sin TTL y evitar duplicados. |
| `POST` | `/auth/login` | Verificar la contraseña, generar un token seguro y crear `session:{token}` con TTL de 5 minutos. |
| `GET` | `/auth/validate` | Leer el Bearer token; devolver `200` y `X-User-Id` si la sesión existe, o `401` en caso contrario. |
| `POST` | `/auth/logout` | Eliminar inmediatamente `session:{token}`; devolver `401` si falta, es inválido, ha caducado o ya fue invalidado. |

Las contraseñas deben almacenarse mediante un hash apropiado, nunca en texto plano. Revisar respuestas para datos ausentes, tipos incorrectos, usuarios duplicados y credenciales inválidas.

## 5. Implementar el microservicio de biblioteca

### 5.1 Cliente MongoDB

En `library-service/app/mongodb_client.py`:

- Crear `pymongo.AsyncMongoClient` usando configuración del entorno.
- Exponer la base de datos y la colección `books`.
- Crear un índice único para `isbn` si resulta necesario.
- Preparar el cierre de la conexión.

### 5.2 Aplicación y poblado

En `library-service/app/__init__.py`:

- Crear la aplicación Quart y registrar las rutas.
- Abrir la conexión asíncrona con MongoDB.
- En un hook como `before_serving`, leer `populate.json` y poblar `books` de forma idempotente para no duplicar datos en cada reinicio.
- Cerrar correctamente el cliente al detener el servicio.

### 5.3 Modelo documental

Cada documento de `books` debe mantener, como mínimo:

- `isbn`, `title`, `author`, `year` y `publisher`.
- `available_stock`, siempre mayor o igual que cero.
- `loan_history`, inicialmente un array vacío.
- Para cada préstamo: `user_id`, `loan_date` y `return_date`; esta última será `null` hasta la devolución.

### 5.4 Rutas protegidas

En `library-service/app/routes.py`, implementar:

| Método | Ruta | Trabajo principal |
| --- | --- | --- |
| `POST` | `/library/books` | Crear un libro con historial vacío. |
| `DELETE` | `/library/books/<isbn>` | Borrar solo si no tiene préstamos activos. |
| `GET` | `/library/books/<isbn>` | Obtener los datos del libro y su historial. |
| `GET` | `/library/loans/active` | Listar préstamos activos del usuario autenticado. |
| `GET` | `/library/loans/history` | Listar el historial del usuario autenticado. |
| `GET` | `/library/books/out-of-stock` | Listar libros cuyo stock sea cero. |
| `POST` | `/library/books/<isbn>/borrow` | Prestar una unidad y añadir una entrada al historial. |
| `POST` | `/library/books/<isbn>/return` | Cerrar el préstamo activo y devolver una unidad al stock. |

Obtener la identidad exclusivamente de `X-User-Id`, que debe haber sido inyectado por Nginx. `library-service` no debe acceder a Redis ni validar tokens.

## 6. Garantizar operaciones atómicas

- Implementar préstamo y devolución con `find_one_and_update()` y un filtro atómico.
- Para prestar, exigir en el propio filtro `available_stock > 0` y evitar un segundo préstamo activo incompatible si así lo requiere el test.
- En la misma actualización, decrementar el stock y añadir el subdocumento con `return_date: null`.
- Para devolver, seleccionar el préstamo activo del usuario y actualizar su `return_date` a la vez que se incrementa el stock.
- No usar secuencias de lectura, comprobación y escritura que permitan carreras.
- Diferenciar correctamente entre libro inexistente, falta de stock y préstamo activo inexistente.

## 7. Crear imágenes de los microservicios

Completar los dos `Dockerfile` y sus `requirements.txt`:

- Usar una versión compatible de Python.
- Instalar solo las dependencias necesarias.
- Ejecutar Quart con Hypercorn.
- Configurar el puerto interno correspondiente.
- Verificar que los imports funcionan con la estructura `app/`.

## 8. Probar por etapas

1. Levantar la infraestructura con `docker compose up --build`.
2. Comprobar el estado con `docker compose ps` y revisar los logs.
3. Probar con `curl` registro, login, validación y logout.
4. Verificar manualmente que el token expira y que logout lo invalida inmediatamente.
5. Probar todos los endpoints de biblioteca a través de `localhost:8080`.
6. Confirmar que no se acepta una cabecera `X-User-Id` falsificada por el cliente.
7. Lanzar peticiones concurrentes de préstamo y confirmar que el stock nunca baja de cero.
8. Crear un entorno virtual solo para los tests, instalar `p3_test_requirements.txt` y ejecutar `pytest` desde la raíz de `p3`.
9. Corregir la implementación, sin modificar los tests oficiales, hasta que toda la batería pase.

## 9. Documentar y recoger evidencias

Guardar en `evidence/` capturas útiles para la memoria:

- `docker compose ps` con todos los servicios activos.
- Registro, login, logout y rechazo de token inválido o caducado.
- Acceso rechazado a biblioteca sin token.
- Alta, consulta y borrado de libros.
- Préstamo, devolución, historial y listado de préstamos activos.
- Intento de borrar un libro con préstamo activo.
- Prueba concurrente que demuestre que el stock no se vuelve negativo.
- Resultado completo de `pytest`.

La memoria debe explicar la arquitectura, las decisiones de diseño, la persistencia en Redis y MongoDB, el flujo de autenticación de Nginx, la atomicidad de los préstamos y las pruebas realizadas.

## 10. Completar el README y preparar la entrega

En `README.txt`, documentar:

- Requisitos previos.
- Variables configurables y puertos.
- Comandos de construcción, arranque, parada y reinicio de datos.
- Ejecución de los tests.
- Ejemplos mínimos de uso.

Antes de crear `P3.zip`:

- Confirmar que la estructura obligatoria y los nombres coinciden con el enunciado.
- Incluir el proyecto, `README.txt` y la memoria en PDF.
- Excluir entornos virtuales, `__pycache__`, bytecode, cachés, secretos y metadatos del sistema operativo.
- Desplegar una última vez desde cero y ejecutar toda la batería de tests.
