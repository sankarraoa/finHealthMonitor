#!/bin/bash
# Setup script for installing and configuring local PostgreSQL on macOS

set -e

echo "🚀 Setting up local PostgreSQL for FinHealthMonitor"
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ This script is designed for macOS. Please install PostgreSQL manually for your OS."
    exit 1
fi

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew is not installed. Please install it first:"
    echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

echo "✅ Homebrew is installed"
echo ""

# Check PostgreSQL version from Railway (if available)
echo "📋 Checking Railway PostgreSQL version..."
RAILWAY_VERSION=""
if command -v psql &> /dev/null; then
    # Try to get version from Railway if DATABASE_URL is set
    if [ -n "$DATABASE_URL" ]; then
        RAILWAY_VERSION=$(psql "$DATABASE_URL" -t -c "SHOW server_version;" 2>/dev/null | xargs | cut -d'.' -f1 || echo "")
    fi
fi

# Default to PostgreSQL 15 if we can't determine version (Railway typically uses 15)
if [ -z "$RAILWAY_VERSION" ]; then
    echo "⚠️  Could not determine Railway PostgreSQL version. Defaulting to PostgreSQL 15."
    echo "   You can check the version by running: python3 test_db_connection.py"
    RAILWAY_VERSION="15"
else
    echo "✅ Railway is using PostgreSQL $RAILWAY_VERSION"
fi

echo ""
echo "📦 Installing PostgreSQL $RAILWAY_VERSION via Homebrew..."

# Install PostgreSQL
brew install postgresql@$RAILWAY_VERSION

echo ""
echo "✅ PostgreSQL $RAILWAY_VERSION installed"
echo ""

# Start PostgreSQL service
echo "🔄 Starting PostgreSQL service..."
brew services start postgresql@$RAILWAY_VERSION

# Wait a moment for service to start
sleep 2

echo ""
echo "📝 Creating database and user..."

# Create database
createdb finhealthmonitor 2>/dev/null || echo "⚠️  Database 'finhealthmonitor' may already exist"

# Set default password for postgres user (if not already set)
echo ""
echo "🔐 Setting up PostgreSQL user..."
echo "   Default password will be 'postgres' (you can change this later)"
echo "   If prompted, enter your macOS password"

# Create .pgpass file for easier connection (optional)
PGPASS_FILE="$HOME/.pgpass"
if [ ! -f "$PGPASS_FILE" ]; then
    echo "localhost:5432:finhealthmonitor:postgres:postgres" > "$PGPASS_FILE"
    chmod 600 "$PGPASS_FILE"
    echo "✅ Created .pgpass file for password-less connections"
fi

echo ""
echo "✅ Local PostgreSQL setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Add to your .env file:"
echo "      USE_LOCAL_DB=true"
echo "      LOCAL_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finhealthmonitor"
echo ""
echo "   2. Run database migrations:"
echo "      alembic upgrade head"
echo ""
echo "   3. Test the connection:"
echo "      python3 -c \"from app.config import config; print('Using:', 'Local' if config.USE_LOCAL_DB else 'Railway')\""
echo ""
echo "💡 To switch back to Railway, set USE_LOCAL_DB=false in your .env file"
echo ""
