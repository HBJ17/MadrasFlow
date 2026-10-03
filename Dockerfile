# Stage 1: build the PWA
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: backend + database + ML + simulation
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/backend:/app/database:/app/ml:/app/simulation
COPY requirements.txt .
RUN pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
COPY . .
COPY --from=frontend /frontend/dist ./frontend/dist
EXPOSE 8000
# Prepares data/DB/models on first start (cached in the data volume), then serves on :8000
CMD ["python", "scripts/demo.py", "--host", "0.0.0.0", "--port", "8000", "--skip-web"]
