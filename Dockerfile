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
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Clone MCP servers from GitHub
RUN git clone https://github.com/XeroAPI/xero-mcp-server.git /app/xero-mcp-server && \
    git clone https://github.com/qboapi/qbo-mcp-server.git /app/quickbooks-mcp-server || \
    echo "QuickBooks MCP server clone failed, will try alternative location"

# Build MCP servers
WORKDIR /app/xero-mcp-server
RUN npm install && npm run build

WORKDIR /app/quickbooks-mcp-server
RUN npm install && npm run build || echo "QuickBooks MCP server build failed, continuing..."

# Copy application code (after MCP servers are cloned and built)
WORKDIR /app
COPY . .

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
