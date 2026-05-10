FROM python:3.11-slim

# Install Tor and system deps
RUN apt-get update && apt-get install -y \
    tor \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all app files
COPY . .

# Make start script executable
RUN chmod +x start.sh

# Expose FastAPI port
EXPOSE 8000

# Start both Tor and FastAPI
CMD ["./start.sh"]
