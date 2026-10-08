# Author: Joonyoung Ki
#
# Multi-stage image for Smart Job AI: stage 1 builds the React dashboard with Node, stage 2 runs the
# FastAPI backend (with Playwright/Chromium for crawling) and serves the built dashboard from frontend/dist.

# ---- Stage 1: Build the React dashboard ----
FROM node:22-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---- Stage 2: FastAPI runtime ----
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

COPY . .
# Bring in only the built static assets; Node itself is not needed at runtime.
COPY --from=frontend-build /frontend/dist ./frontend/dist

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
