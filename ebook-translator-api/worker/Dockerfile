FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends calibre \
    && rm -rf /var/lib/apt/lists/*

COPY ebook-translator-api/worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app/calibre_plugins/ebook_translator
COPY ebook-translator-api/worker/app /app/worker_app
COPY ebook-translator-api/common /app/common

ENV PYTHONPATH=/app:/usr/lib/calibre:/usr/lib/python3/dist-packages

CMD ["celery", "-A", "worker_app.celery_app:celery_app", "worker", "--loglevel=INFO", "-Q", "ebook.jobs.default"]
