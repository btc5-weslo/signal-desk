# Demo API image for Render (free plan). Build context: repository root.
#   docker build -f deploy/api.Dockerfile -t signal-api .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python3.11 \
    SIGNAL_DATA_DIR=/app/store

RUN pip install --no-cache-dir uv==0.13.9

WORKDIR /app
COPY shared/ shared/
COPY data/ data/
COPY quant/ quant/
COPY qa/ qa/
COPY backend/ backend/
COPY deploy/ deploy/

# Install from the backend's own lockfile (pulls shared/data/quant as path deps).
RUN cd backend && uv sync --frozen --no-dev

# Bake a recent store into the image so a cold start serves candles at once.
# Fails the build if any series cannot be fetched and verified.
RUN backend/.venv/bin/python deploy/bootstrap_data.py build --out "$SIGNAL_DATA_DIR"

RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh", "deploy/start-api.sh"]
