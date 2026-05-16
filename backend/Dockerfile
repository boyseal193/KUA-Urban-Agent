# Monorepo root build — copies full repo so legacy domain modules + ``backend/`` are on PYTHONPATH.
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY . /app

WORKDIR /app/backend

EXPOSE 8000

# Railway/Render expose ``PORT``; default 8000 for local/Docker.
CMD ["sh", "-c", "gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-4} -b 0.0.0.0:${PORT:-8000} --timeout 180 --graceful-timeout 30 --access-logfile - --error-logfile -"]
