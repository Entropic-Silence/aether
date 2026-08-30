FROM python:3.11-slim

WORKDIR /app
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api ./
WORKDIR /app

EXPOSE 8123
CMD ["uvicorn", "aether_api.main:app", "--host", "0.0.0.0", "--port", "8123"]
