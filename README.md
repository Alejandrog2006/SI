# Práctica 1: servicios de usuarios y documentos

Autores: Manuel Salvador Mayor (`tassburr-pixel`) y Alejandro (`Alejandrog2006`).

## Descripción

El proyecto implementa dos servicios HTTP independientes con Quart:

- `user_service`: crea usuarios, realiza el login y modifica contraseñas.
- `file_service`: crea, modifica, lista, recupera y elimina documentos, y cambia su visibilidad.

Los datos se mantienen en memoria. Al reiniciar los servicios se eliminan los usuarios y documentos creados.

## Estructura

```text
cliente/
  cliente.py          Cliente de ejemplo no interactivo
  comprobadores.py    Comprobaciones automáticas de las rutas
user_service/
  user.py             Servicio de usuarios
  Dockerfile
  requirements.txt
file_service/
  file.py             Servicio de documentos
  Dockerfile
  requirements.txt
docker-compose.yml
```

## Puertos

- Servicio de usuarios: `http://localhost:5050`
- Servicio de documentos: `http://localhost:5051`

## Autenticación

Al crear un usuario o iniciar sesión se devuelve su `uid` y un `token`. Las operaciones protegidas reciben el token mediante esta cabecera:

```http
Authorization: Bearer <token>
```

Los dos servicios deben recibir el mismo `SECRET_UUID`. Docker Compose ya configura esta variable para ambos contenedores.

Para ejecutar los servicios directamente, hay que definirla antes:

```bash
export SECRET_UUID=12345678-1234-5678-1234-567812345678
```

## Rutas

### Usuarios

| Método | Ruta | Operación |
| --- | --- | --- |
| `PUT` | `/user` | Crear un usuario |
| `POST` | `/user` | Iniciar sesión |
| `PATCH` | `/user` | Modificar la contraseña del usuario autenticado |

### Documentos

| Método | Ruta | Operación |
| --- | --- | --- |
| `GET` | `/file/<uid>` | Listar los documentos del propietario |
| `PUT` | `/file/<uid>/<filename>` | Crear o modificar un documento |
| `GET` | `/file/<uid>/<filename>` | Recuperar un documento |
| `DELETE` | `/file/<uid>/<filename>` | Eliminar un documento |
| `PATCH` | `/file/<uid>/<filename>` | Cambiar la visibilidad con `{"public": true/false}` |

Los documentos se crean como privados. Solamente el propietario puede administrarlos. Un documento público puede recuperarse sin autenticación conociendo el `uid` y el nombre del archivo.

## Ejecución con Docker

Construir y arrancar los servicios:

```bash
docker-compose build
docker-compose up -d
docker-compose ps
```

Consultar los registros:

```bash
docker-compose logs
```

Detenerlos:

```bash
docker-compose down
```

## Ejecución local

Crear y activar un entorno virtual e instalar las dependencias:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r user_service/requirements.txt
pip install -r file_service/requirements.txt
export SECRET_UUID=12345678-1234-5678-1234-567812345678
```

Iniciar cada servicio en una terminal distinta:

```bash
python user_service/user.py
python file_service/file.py
```

## Cliente y comprobaciones

Con los dos servicios iniciados, ejecutar el cliente de ejemplo:

```bash
python cliente/cliente.py
```

Ejecutar las comprobaciones automáticas:

```bash
python cliente/comprobadores.py
```

El comprobador crea usuarios con nombres únicos, recorre todas las operaciones y termina con código `1` si alguna comprobación falla.
