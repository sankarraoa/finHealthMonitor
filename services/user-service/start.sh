#!/bin/bash
set -e

# Run database migrations (continue even if revision not found - tables may already exist)
echo "Running database migrations..."
alembic upgrade head || {
    echo "Warning: Migration failed, but continuing (tables may already exist)"
    # Try to stamp the database to the current head if it's not already there
    alembic stamp head 2>/dev/null || true
}

# Start the application
echo "Starting user-service..."
exec python -m app.main
