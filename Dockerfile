# Use Python 3.13 slim image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Build MCP servers
WORKDIR /app/xero-mcp-server
RUN npm install && npm run build

WORKDIR /app/quickbooks-mcp-server
RUN npm install && npm run build

# Return to app directory
WORKDIR /app

# Make start script executable
COPY start.sh .
RUN chmod +x start.sh

# Expose port (Railway will set PORT env var)
EXPOSE 8000

# Health check (Railway has its own health checks, but we can add one here)
# HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
#     CMD python -c "import requests; requests.get('http://localhost:${PORT:-8000}/')" || exit 1

# Start the application (migrations run in start.sh)
CMD ["./start.sh"]
