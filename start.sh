#!/bin/bash
set -e

# Copy custom torrc
if [ -f /app/torrc ]; then
    cp /app/torrc /etc/tor/torrc
fi

# Create tor data dir and set permissions
mkdir -p /var/lib/tor
chmod 700 /var/lib/tor

# Start Tor in background
echo "[INFO] Starting Tor proxy..."
tor -f /etc/tor/torrc &
TOR_PID=$!

# Wait for Tor to bootstrap (check SOCKS port first)
echo "[INFO] Waiting for Tor SOCKS port..."
for i in {1..30}; do
    if curl --silent --socks5-hostname 127.0.0.1:9050 https://api.ipify.org?format=json > /dev/null 2>&1; then
        echo "[INFO] Tor SOCKS is ready!"
        break
    fi
    sleep 1
done

# Wait for control cookie file
echo "[INFO] Waiting for Tor control cookie..."
for i in {1..30}; do
    if [ -f /var/lib/tor/control_auth_cookie ]; then
        chmod 644 /var/lib/tor/control_auth_cookie
        echo "[INFO] Tor control cookie ready!"
        break
    fi
    sleep 1
done

# Show initial Tor IP
echo "[INFO] Initial Tor IP:"
curl --silent --socks5-hostname 127.0.0.1:9050 https://api.ipify.org?format=json || true
echo ""

# Start IP rotator in background
echo "[INFO] Starting IP rotator..."
python3 /app/rotator.py &
ROTATOR_PID=$!

# Start FastAPI
echo "[INFO] Starting FastAPI server..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
