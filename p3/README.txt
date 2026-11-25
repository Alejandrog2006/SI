# Práctica 3: Microservicios Avanzados y BBDD NoSQL

Autores: Manuel Salvador Mayor (`tassburr-pixel`) y Alejandro González García (`Alejandrog2006`).

---

## 1. Descripción General

El proyecto implementa un sistema distribuido y desacoplado basado en una arquitectura de microservicios API REST asíncronos desplegados en **5 contenedores independientes** mediante Docker Compose:

1. **`api-gateway` (Nginx):** Único punto de entrada público al sistema (`http://localhost:8080`). Actúa como proxy inverso y centraliza la autorización mediante sub-peticiones internas `auth_request`.
2. **`auth-service` (Quart + Hypercorn):** Microservicio encargado del registro permanente de usuarios, inicio de sesión, validación de tokens e invalidación inmediata (logout).
3. **`redis` (Redis 7 Alpine):** Base de datos NoSQL clave-valor para `auth-service`, con persistencia en disco AOF (`--appendonly yes`) para usuarios y expiración automática (TTL) para sesiones.
4. **`library-service` (Quart + Hypercorn):** Microservicio encargado del catálogo de libros y la gestión atómica de préstamos y devoluciones.
5. **`mongodb` (MongoDB 7):** Base de datos NoSQL documental para `library-service`, con persistencia en volumen y poblado inicial automático e idempotente.

---

## 2. Estructura del Proyecto

```text
p3/
├── api-gateway/
│   └── nginx.conf                  # Configuración de Nginx (rutas, auth_request e inyección de X-User-Id)
├── auth-service/
│   ├── app/
│   │   ├── __init__.py             # Inicialización de Quart, ciclo de vida de Redis y errores HTTP en JSON
│   │   ├── redis_client.py         # Cliente asíncrono de Redis (redis.asyncio)
│   │   └── routes.py               # Endpoints: register, login, validate y logout
│   ├── Dockerfile                  # Imagen Python 3.12 ejecutada con Hypercorn (:5050)
│   └── requirements.txt            # Dependencias del servicio de autenticación
├── library-service/
│   ├── app/
│   │   ├── __init__.py             # Inicialización de Quart, poblado idempotente y errores HTTP en JSON
│   │   ├── mongodb_client.py       # Cliente asíncrono de MongoDB (pymongo.AsyncMongoClient)
│   │   ├── populate.json           # Datos iniciales oficiales para poblar la colección books
│   │   └── routes.py               # Endpoints protegidos de libros y préstamos atómicos
│   ├── Dockerfile                  # Imagen Python 3.12 ejecutada con Hypercorn (:5051)
│   └── requirements.txt            # Dependencias del servicio de biblioteca
├── docker-compose.yml              # Orquestación completa de los 5 contenedores, volúmenes y red
├── pytest.ini                      # Configuración de pytest (addopts = -p no:asyncio)
├── p3_test.py                      # Batería oficial de tests end-to-end
├── p3_test_requirements.txt        # Dependencias para ejecutar los tests (pytest, anyio, httpx)
└── README.txt                      # Documentación de arquitectura, despliegue y pruebas
```

---

## 3. Requisitos Previos y Configuración

### Requisitos
- **Docker** y **Docker Compose**.
- **Python 3.12+** (con `venv`) en la máquina local únicamente para ejecutar la batería de tests (`pytest`).
- **`curl`** (opcional) para realizar comprobaciones manuales desde la terminal.

### Puertos y Variables Configurables
Solo el contenedor `api-gateway` publica un puerto hacia la máquina anfitriona. Los microservicios y bases de datos permanecen aislados dentro de la red privada `app-network`:

| Variable | Valor por defecto | Descripción |
| --- | --- | --- |
| `GATEWAY_PORT` | `8080` | Puerto público expuesto en el host por Nginx (`localhost:8080`) |
| `AUTH_PORT` | `5050` | Puerto interno de `auth-service` dentro de `app-network` |
| `LIBRARY_PORT` | `5051` | Puerto interno de `library-service` dentro de `app-network` |
| `REDIS_HOST` / `REDIS_PORT` | `redis` / `6379` | Host y puerto internos del contenedor de Redis |
| `SESSION_TTL_SECONDS` | `300` | Tiempo de vida (TTL) de los tokens de sesión (5 minutos) |
| `MONGO_HOST` / `MONGO_PORT` | `mongodb` / `27017` | Host y puerto internos del contenedor de MongoDB |
| `MONGO_DATABASE` | `library` | Nombre de la base de datos utilizada en MongoDB |

Si el puerto `8080` estuviese ocupado en el equipo local, puede cambiarse al arrancar sin editar ficheros:
```bash
GATEWAY_PORT=8081 docker compose up --build -d
```

---

## 4. Explicación Detallada de la Implementación Punto por Punto

### 4.1. Despliegue, Red Interna y Contenedores (`docker-compose.yml` y `Dockerfile`)
- **Aislamiento de red:** Los cinco servicios están conectados a una red puente privada (`app-network`). Únicamente `api-gateway` define `ports` (`8080:8080`); `auth-service` y `library-service` utilizan `expose`, y ni Redis ni MongoDB publican puertos al exterior, impidiendo accesos directos desde el host.
- **Orden de arranque y salud (`healthcheck`):** Redis (`redis-cli ping`) y MongoDB (`mongosh ... db.adminCommand('ping')`) incluyen comprobaciones de salud periódicas. Los microservicios dependen de ellas mediante `depends_on` con `condition: service_healthy`.
- **Persistencia en disco:** Se montan dos volúmenes con nombre (`redis-data:/data` y `mongodb-data:/data/db`) que conservan los usuarios registrados, el catálogo y los préstamos aunque se detengan o reinicien los contenedores.
- **Servidor ASGI Hypercorn:** Ambos microservicios corren sobre `python:3.12-slim` lanzando Quart mediante `CMD ["hypercorn", "app:app", "--bind", "0.0.0.0:<puerto>", "--reload"]`, escuchando en todas las interfaces internas del contenedor y permitiendo recarga automática. En la construcción (`build`) se especifica `network: host` para facilitar la descarga de dependencias.
- **Respuestas de error en JSON:** En los dos `app/__init__.py` se registra un manejador `@application.errorhandler(HTTPException)` que intercepta cualquier excepción HTTP estándar (como `404 Not Found` o `405 Method Not Allowed`) y la devuelve en formato JSON en lugar de páginas HTML.

### 4.2. API Gateway y Autorización Delegada (`api-gateway/nginx.conf`)
- **Rutas de autenticación (`/auth/`):** Nginx redirige las peticiones directamente a `http://auth-service:5050` reenviando la cabecera `Authorization`.
- **Sub-petición interna (`location = /auth/validate`):** Marcada con `internal;` para que ningún cliente externo pueda invocarla directamente. Descarta el cuerpo de la petición (`proxy_pass_request_body off`) y envía únicamente la cabecera `Authorization` a `auth-service:5050/auth/validate`, limpiando cualquier `X-User-Id` previo.
- **Protección de biblioteca (`/library/`):**
  1. Ejecuta `auth_request /auth/validate;`. Si `auth-service` responde `401`, Nginx rechaza inmediatamente la solicitud del cliente con `401 Unauthorized` sin contactar con `library-service`.
  2. Si `auth-service` responde `200 OK`, Nginx extrae la cabecera `X-User-Id` devuelta por la sub-petición mediante `auth_request_set $user_id $upstream_http_x_user_id;`.
  3. Sobrescribe cualquier cabecera `X-User-Id` que hubiese enviado el cliente (`proxy_set_header X-User-Id $user_id;`) evitando suplantaciones de identidad, y encamina la petición a `http://library-service:5051`.

### 4.3. Microservicio de Autenticación y Modelo en Redis (`auth-service`)
- **Conexión asíncrona (`redis_client.py`):** Emplea `redis.asyncio` con `decode_responses=True`, gestionando la inicialización en `@application.before_serving` y el cierre limpio con `aclose()` en `@application.after_serving`.
- **Doble rol de datos en Redis:**
  1. **Usuarios permanentes (`user:{username}`):** Almacenados como estructuras **`HASH`** con los campos `username`, `password_hash` (generado de forma segura con `werkzeug.security.generate_password_hash`, nunca en texto plano) y `email`. No tienen TTL y persisten en disco gracias a `--appendonly yes` (AOF).
  2. **Sesiones temporales (`session:{token}`):** Almacenadas como claves **`STRING`** cuyo valor es el `username`, con un **TTL de 300 segundos (5 minutos)** (`ex=300`). Como cada sesión se indexa por su propio token (`secrets.token_urlsafe(32)`), un mismo usuario puede mantener varias sesiones simultáneas independientes.
- **Endpoints implementados (`routes.py`):**
  - `POST /auth/register`: Valida tipos y campos no vacíos (`400`), comprueba duplicados con `exists` (`409`) y almacena el `HASH` (`201`).
  - `POST /auth/login`: Recupera el `HASH` con `hgetall`, verifica la contraseña con `check_password_hash` (`401` si falla) y crea `session:{token}` con TTL de 5 minutos devolviendo `{"token": ...}` (`200`).
  - `GET /auth/validate`: Extrae el Bearer token, consulta `session:{token}` en Redis y devuelve `200` con la cabecera `X-User-Id: <username>` o `401` si falta/expiró.
  - `POST /auth/logout`: Elimina en el acto `session:{token}` mediante `delete()`. Si borra la clave devuelve `200`; si faltaba la cabecera, el token no existía, había expirado o ya se había cerrado sesión antes (`deleted_count == 0`), devuelve `401`.

### 4.4. Microservicio de Biblioteca, Poblado y Atomicidad en MongoDB (`library-service`)
- **Conexión e índices (`mongodb_client.py`):** Usa el cliente asíncrono oficial `pymongo.AsyncMongoClient`, verifica conectividad mediante `ping` y crea un índice único sobre `isbn` en la colección `books`.
- **Poblado automático e idempotente (`__init__.py`):** En el hook `@application.before_serving`, tras conectar con MongoDB, lee `populate.json`, convierte las cadenas ISO UTC (`...Z`) a objetos `datetime` reales y ejecuta por cada libro:
  ```python
  await collection.update_one(
      {"isbn": document["isbn"]},
      {"$setOnInsert": document},
      upsert=True,
  )
  ```
  De este modo, en el primer arranque inserta los 12 libros iniciales, y en sucesivos reinicios no genera duplicados ni sobrescribe el stock o los préstamos ya realizados.
- **Desacoplamiento de identidad:** `library-service` no accede a Redis ni valida tokens; obtiene al usuario exclusivamente de la cabecera `X-User-Id` inyectada por Nginx (`@library_bp.before_request`).
- **Modelo documental y aislamiento:** Cada documento de `books` mantiene `isbn`, `title`, `author`, `year`, `publisher`, `available_stock` y el array embebido `loan_history` (`user_id`, `loan_date`, `return_date`). En `/library/loans/active` y `/library/loans/history` se filtran las entradas de `loan_history` para que cada usuario vea únicamente sus propios préstamos.
- **Operaciones atómicas libres de condiciones de carrera (`routes.py`):**
  - **Préstamo (`POST /library/books/<isbn>/borrow`):** Utiliza una única llamada `find_one_and_update()` cuyo filtro exige simultáneamente que el `isbn` exista, que `available_stock` sea estrictamente mayor que cero (`{"$gt": 0}`) y que el usuario no tenga ya un préstamo activo (`return_date: None`) de ese mismo ejemplar. En la misma operación atómica aplica `"$inc": {"available_stock": -1}` y `"$push"` del nuevo préstamo con `return_date: None`. Así es imposible que peticiones concurrentes dejen el stock en valores negativos.
  - **Devolución (`POST /library/books/<isbn>/return`):** Utiliza `find_one_and_update()` buscando en `loan_history` con `$elemMatch` el préstamo activo del usuario (`user_id` y `return_date: None`), incrementando el stock (`"$inc": {"available_stock": 1}`) y fijando la fecha de devolución (`"$set": {"loan_history.$.return_date": now}`) en un solo paso atómico.
  - **Borrado seguro (`DELETE /library/books/<isbn>`):** Usa `find_one_and_delete()` condicionando a que no exista ningún elemento en `loan_history` con `return_date: None`, devolviendo `409 Conflict` si el libro tiene algún préstamo activo.

---

## 5. Instrucciones Paso a Paso de Ejecución

Todos los comandos siguientes deben ejecutarse desde la carpeta raíz de la práctica (`p3/`):

### Paso 1: Construir imágenes y levantar los 5 contenedores
```bash
docker compose up --build -d
```

### Paso 2: Verificar el estado de los contenedores y logs
Comprobar que los 5 servicios están en ejecución y que `redis` y `mongodb` figuran como `(healthy)`:
```bash
docker compose ps
```
Para consultar los registros en tiempo real:
```bash
docker compose logs -f
```

### Paso 3: Preparar el entorno virtual y ejecutar la batería de tests (`pytest`)
Crear un entorno virtual local para las pruebas, instalar las dependencias oficiales y lanzar `pytest` (que toma automáticamente la configuración de `pytest.ini`):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r p3_test_requirements.txt
pytest -v
```
Para salir del entorno virtual al terminar:
```bash
deactivate
```

### Paso 4: Detener los servicios y gestión de datos
- **Detener los contenedores conservando los datos persistentes (usuarios y préstamos):**
  ```bash
  docker compose down
  ```
- **Detener los contenedores y reiniciar por completo las bases de datos (borrando volúmenes):**
  ```bash
  docker compose down -v
  ```

---

## 6. Ejemplos Mínimos de Uso con `curl`

### 1. Registrar un usuario (`201 Created`)
```bash
curl -i -X POST http://localhost:8080/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "ana", "password": "secret123", "email": "ana@example.com"}'
```

### 2. Iniciar sesión y guardar el token (`200 OK`)
```bash
TOKEN=$(curl -s -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "ana", "password": "secret123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
```

### 3. Consultar un libro poblado inicialmente (`200 OK`)
```bash
curl -i http://localhost:8080/library/books/978-0451524935 \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Crear un nuevo libro (`201 Created`)
```bash
curl -i -X POST http://localhost:8080/library/books \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "isbn": "978-84-376-0494-7",
    "title": "Cien años de soledad",
    "author": "Gabriel García Márquez",
    "year": 1967,
    "publisher": "Cátedra",
    "available_stock": 2
  }'
```

### 5. Pedir prestado un libro, listar préstamos activos y devolverlo (`200 OK`)
```bash
# Tomar en préstamo
curl -i -X POST http://localhost:8080/library/books/978-84-376-0494-7/borrow \
  -H "Authorization: Bearer $TOKEN"

# Listar préstamos activos del usuario autenticado
curl -i http://localhost:8080/library/loans/active \
  -H "Authorization: Bearer $TOKEN"

# Devolver el libro
curl -i -X POST http://localhost:8080/library/books/978-84-376-0494-7/return \
  -H "Authorization: Bearer $TOKEN"

# Consultar historial de préstamos del usuario
curl -i http://localhost:8080/library/loans/history \
  -H "Authorization: Bearer $TOKEN"
```

### 6. Cerrar sesión e invalidar el token inmediatamente (`200 OK`)
```bash
curl -i -X POST http://localhost:8080/auth/logout \
  -H "Authorization: Bearer $TOKEN"
```
