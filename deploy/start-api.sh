#!/bin/sh
# Render start command for the demo API.
# The image already holds a store built at deploy time. Top it up with the
# newest daily archives in the background so the port opens right away.
set -eu
cd /app
: "${SIGNAL_DATA_DIR:?set SIGNAL_DATA_DIR}"
if [ "${SIGNAL_REFRESH_ON_START:-1}" = "1" ]; then
  backend/.venv/bin/python deploy/bootstrap_data.py topup >/tmp/bootstrap.log 2>&1 &
fi
cd backend
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
