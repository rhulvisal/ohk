FROM python:3.11-slim

# Install Tor and dependencies
RUN apt-get update && apt-get install -y \
    tor \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . /app
WORKDIR /app

# Tor config for 10-second IP rotation
RUN echo "SocksPort 0.0.0.0:9050" >> /etc/tor/torrc && \
    echo "MaxCircuitDirtiness 10" >> /etc/tor/torrc && \
    echo "NewCircuitPeriod 10" >> /etc/tor/torrc

# Start script to run both Tor and Uvicorn
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8000

CMD ["/start.sh"]
