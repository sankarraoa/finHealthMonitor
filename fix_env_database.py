#!/usr/bin/env python3
"""
Script to fix database configuration in .env file.
"""
import os
import re
from pathlib import Path

def fix_env_file():
    env_path = Path(".env")
    
    if not env_path.exists():
        print("❌ .env file not found!")
        print("Creating .env file with local database configuration...")
        with open(env_path, "w") as f:
            f.write("# Database Configuration\n")
            f.write("USE_LOCAL_DB=true\n")
            f.write("LOCAL_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finhealthmonitor\n")
        print("✅ Created .env file with USE_LOCAL_DB=true")
        return
    
    # Read the file
    with open(env_path, "r") as f:
        content = f.read()
    
    lines = content.split("\n")
    modified = False
    new_lines = []
    
    for line in lines:
        # Check if RAILWAY_DATABASE_URL has placeholder
        if line.startswith("RAILWAY_DATABASE_URL=") and (":port" in line or "/port/" in line or line.endswith(":port")):
            print(f"❌ Found placeholder in: {line}")
            print("   → Commenting out this line. You can uncomment and fix it later if needed.")
            new_lines.append(f"# {line}  # FIXED: Had placeholder 'port'")
            modified = True
        # Check if USE_LOCAL_DB is set
        elif line.startswith("USE_LOCAL_DB="):
            if "true" not in line.lower():
                print(f"⚠️  Found: {line}")
                print("   → Updating to USE_LOCAL_DB=true for local development")
                new_lines.append("USE_LOCAL_DB=true")
                modified = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # If USE_LOCAL_DB wasn't found, add it
    if not any("USE_LOCAL_DB" in line for line in new_lines):
        print("⚠️  USE_LOCAL_DB not found, adding it...")
        # Add after any comments at the top
        insert_pos = 0
        for i, line in enumerate(new_lines):
            if line.strip() and not line.strip().startswith("#"):
                insert_pos = i
                break
        new_lines.insert(insert_pos, "USE_LOCAL_DB=true")
        modified = True
    
    if modified:
        # Write back
        with open(env_path, "w") as f:
            f.write("\n".join(new_lines))
        print("\n✅ Fixed .env file!")
        print("   - Set USE_LOCAL_DB=true")
        print("   - Commented out RAILWAY_DATABASE_URL with placeholder")
        print("\nYour app should now use the local database.")
        print("Make sure PostgreSQL is running on localhost:5432")
    else:
        print("✅ .env file looks good! No changes needed.")

if __name__ == "__main__":
    fix_env_file()
