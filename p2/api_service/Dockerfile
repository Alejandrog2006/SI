# Imagen pequeña que ya incluye Python 3.12.
FROM python:3.12-slim

# Directorio de trabajo del servicio dentro del contenedor.
WORKDIR /app

# Instala Quart, SQLAlchemy y asyncpg antes de copiar el codigo de la API.
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copia el modulo que publica las rutas de peliculas y compras.
COPY api_service/api.py ./api.py

# Documenta el puerto interno utilizado por api.py.
EXPOSE 5051

# Inicia la API al arrancar el contenedor.
CMD ["python", "api.py"]
