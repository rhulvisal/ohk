#!/bin/bash
set -e

# Copy custom torrc if it exists
if [ -f /app/torrc ]; then
    cp /app/torrc /etc/tor/torrc
fi

# Start Tor in background
echo "[INFO] Starting Tor proxy..."
tor &
TOR_PID=$!

# Wait for Tor to bootstrap (check SOCKS port)
echo "[INFO] Waiting for Tor to be ready..."
for i in {1..30}; do
    if curl --silent --socks5-hostname 127.0.0.1:9050 https://api.ipify.org?format=json > /dev/null 2>&1; then
        echo "[INFO] Tor is ready!"
        break
    fi
    sleep 1
done

# Show initial Tor IP
echo "[INFO] Current Tor IP:"
curl --silent --socks5-hostname 127.0.0.1:9050 https://api.ipify.org?format=json || true

# Start FastAPI on Railway's PORT or default 8000
echo "[INFO] Starting FastAPI server..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
