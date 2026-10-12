FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY config ./config
COPY orders_stock ./orders_stock
COPY scripts ./scripts
COPY manage.py ./

RUN pip install --no-cache-dir ".[dev]"

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
