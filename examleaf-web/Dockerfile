# ExamLeaf web: one image for web (gunicorn), worker and beat (Celery); see docker-compose.yml.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Static files are collected into the image (hashed and compressed, served by WhiteNoise); the key is a build-time dummy.
RUN SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput \
    && useradd --system --uid 1000 --no-create-home examleaf \
    && mkdir -p media && chown examleaf media
USER examleaf

EXPOSE 8000
# WEB_CONCURRENCY sets the number of gunicorn workers (default 1).
CMD ["gunicorn", "examleaf.wsgi", "--bind", "0.0.0.0:8000", "--max-requests", "1000", "--max-requests-jitter", "100"]
