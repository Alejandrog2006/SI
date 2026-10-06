FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY file.py .

EXPOSE 5051

CMD ["python", "file.py"]
