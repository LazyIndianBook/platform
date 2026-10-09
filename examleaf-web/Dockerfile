# ExamLeaf web: one image for web (gunicorn), worker and beat (Celery); see docker-compose.yml.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# WeasyPrint (invoice PDFs) needs Pango and HarfBuzz, a font with the rupee sign (DejaVu Sans) and fonts for the names
# and addresses customers type in their own script (Noto: Assamese and Bengali, Devanagari ...): the address is printed
# on the invoice, and without such a font the letters come out as empty boxes.
# ffmpeg (and ffprobe) make the revision course's clips into HLS (learn/media.py) on the media worker.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
        fonts-dejavu-core fonts-noto-core \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# What the site runs on only: the test and lint tools are in requirements-dev.txt.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Static files are collected into the image (hashed and compressed, served by WhiteNoise); the key is a build-time dummy
# (50 characters at least, or settings.py refuses to start).
RUN SECRET_KEY=build-time-dummy-for-collectstatic-only-not-used-at-run-time python manage.py collectstatic --noinput \
    && useradd --system --uid 1000 --no-create-home examleaf \
    && mkdir -p media && chown examleaf media
USER examleaf
# Fontconfig keeps WeasyPrint's font cache in /tmp (the user has no home folder; the chart's root is read-only), not
# nowhere: without it every invoice printed "No writable cache directories".
ENV XDG_CACHE_HOME=/tmp/.cache

EXPOSE 8000
# gunicorn.conf.py: processes (WEB_CONCURRENCY, default 2) of 8 threads, the timeouts, recycling and JSON logs, each
# from the environment (RESILIENCE.md).
CMD ["gunicorn", "--config", "gunicorn.conf.py", "examleaf.wsgi"]
