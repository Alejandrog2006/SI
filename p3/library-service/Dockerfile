FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 5051

CMD ["hypercorn", "app:app", "--bind", "0.0.0.0:5051"]