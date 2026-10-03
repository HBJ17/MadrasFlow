# Stage 1: build the PWA
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: API + twin + predictor
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
COPY . .
COPY --from=web /web/dist ./web/dist
EXPOSE 8000
# Prepares data/DB/models on first start (cached in the data volume), then serves on :8000
CMD ["python", "scripts/demo.py", "--host", "0.0.0.0", "--port", "8000", "--skip-web"]
