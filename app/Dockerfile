FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY factory ./factory

RUN useradd --system --uid 10001 factory
USER factory

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s CMD ["python", "-m", "factory.health"]
CMD ["python", "-m", "factory.worker"]
