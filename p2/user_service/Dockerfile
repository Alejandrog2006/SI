# Imagen pequeña que ya incluye Python 3.12.
FROM python:3.12-slim

# Todas las rutas siguientes se resuelven desde /app dentro del contenedor.
WORKDIR /app

# Copiar primero las dependencias permite reutilizar esta capa entre compilaciones.
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# El servicio solo necesita su propio modulo Python para ejecutarse.
COPY user_service/user.py ./user.py

# Documenta el puerto interno en el que escucha Quart.
EXPOSE 5050

# Inicia el servicio al arrancar el contenedor.
CMD ["python", "user.py"]
