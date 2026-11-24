FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=pip_ca \
    if [ -f /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi \
    && pip install --no-cache-dir --no-compile -r requirements.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --home-dir /app app \
    && install -d -o app -g app /app/media /app/staticfiles /app/runtime
COPY --chown=app:app . .
USER app
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--access-logformat", "%(m)s %(U)s %(s)s"]
