#!/bin/bash
set -e

# Copy custom torrc
if [ -f /app/torrc ]; then
    cp /app/torrc /etc/tor/torrc
fi

# Start Tor in background
echo "[INFO] Starting Tor proxy..."
tor -f /etc/tor/torrc &
TOR_PID=$!

# Wait for Tor to bootstrap
echo "[INFO] Waiting for Tor control port..."
for i in {1..30}; do
    if echo "" | nc -w 1 127.0.0.1 9051 2>/dev/null; then
        echo "[INFO] Tor control port is ready!"
        break
    fi
    sleep 1
done

# Show initial Tor IP
echo "[INFO] Initial Tor IP:"
curl --silent --socks5-hostname 127.0.0.1:9050 https://api.ipify.org?format=json || true
echo ""

# Start IP rotator in background (forces NEWNYM every 10 seconds)
echo "[INFO] Starting IP rotator..."
python3 /app/rotator.py &
ROTATOR_PID=$!

# Start FastAPI
echo "[INFO] Starting FastAPI server..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
