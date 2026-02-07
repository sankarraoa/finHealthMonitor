#!/usr/bin/env python3
"""
Helper script to diagnose and fix database configuration issues.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("=" * 60)
print("Database Configuration Diagnostic")
print("=" * 60)
print()

# Check DATABASE_URL
database_url = os.getenv("DATABASE_URL")
if database_url:
    print(f"✓ DATABASE_URL is set: {database_url[:50]}...")
    if ':port' in database_url or '/port/' in database_url or database_url.endswith(':port'):
        print("  ❌ ERROR: DATABASE_URL contains placeholder 'port' instead of actual port number!")
        print("  → Solution: Unset DATABASE_URL or set it with a real port number")
        print()
else:
    print("✓ DATABASE_URL is not set (will use USE_LOCAL_DB setting)")
    print()

# Check USE_LOCAL_DB
use_local_db = os.getenv("USE_LOCAL_DB", "false").lower() == "true"
print(f"USE_LOCAL_DB: {use_local_db}")
print()

# Check LOCAL_DATABASE_URL
local_db_url = os.getenv("LOCAL_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/finhealthmonitor")
print(f"LOCAL_DATABASE_URL: {local_db_url}")
if ':port' in local_db_url or '/port/' in local_db_url or local_db_url.endswith(':port'):
    print("  ❌ ERROR: LOCAL_DATABASE_URL contains placeholder 'port'!")
    print("  → Solution: Set LOCAL_DATABASE_URL with a real port number (e.g., 5432)")
print()

# Check RAILWAY_DATABASE_URL
railway_db_url = os.getenv("RAILWAY_DATABASE_URL", "postgresql://postgres:nIrSLrxNUhzPghZJiuKVwGwcFMxiAzgh@metro.proxy.rlwy.net:10176/railway")
print(f"RAILWAY_DATABASE_URL: {railway_db_url[:60]}...")
if ':port' in railway_db_url or '/port/' in railway_db_url or railway_db_url.endswith(':port'):
    print("  ❌ ERROR: RAILWAY_DATABASE_URL contains placeholder 'port'!")
    print("  → Solution: Set RAILWAY_DATABASE_URL with a real port number from Railway dashboard")
print()

print("=" * 60)
print("Recommended Fix:")
print("=" * 60)
print()

if database_url and (':port' in database_url or '/port/' in database_url or database_url.endswith(':port')):
    print("Option 1: Unset DATABASE_URL and use USE_LOCAL_DB")
    print("  Add to your .env file:")
    print("  USE_LOCAL_DB=true")
    print("  # Remove or comment out: DATABASE_URL=...")
    print()
    print("Option 2: Fix DATABASE_URL with actual port number")
    print("  DATABASE_URL=postgresql://username:password@host:5432/database")
    print("  (Replace 5432 with your actual PostgreSQL port)")
    print()
else:
    if use_local_db:
        print("Using local database. Make sure PostgreSQL is running on port 5432")
        print("  LOCAL_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finhealthmonitor")
    else:
        print("Using Railway database. Make sure RAILWAY_DATABASE_URL has a valid port number")
        print("  Get the connection string from Railway dashboard")
    print()

print("To create/update .env file, copy DATABASE_CONFIG_EXAMPLE.txt and update values")
