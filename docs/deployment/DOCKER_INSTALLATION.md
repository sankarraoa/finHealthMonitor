# Docker Installation Guide for macOS

## Option 1: Download Docker Desktop Directly (Recommended)

1. **Download Docker Desktop for Mac**
   - Go to: https://www.docker.com/products/docker-desktop/
   - Click "Download for Mac"
   - Choose the version for your Mac:
     - **Apple Silicon (M1/M2/M3)**: Download "Mac with Apple chip"
     - **Intel**: Download "Mac with Intel chip"

2. **Install Docker Desktop**
   - Open the downloaded `.dmg` file
   - Drag Docker.app to your Applications folder
   - Open Docker.app from Applications
   - Follow the setup wizard
   - You may need to enter your password to install system components

3. **Start Docker Desktop**
   - Docker Desktop will start automatically
   - Wait for it to fully start (you'll see a whale icon in the menu bar)
   - The icon should be steady (not animated) when ready

4. **Verify Installation**
   ```bash
   docker --version
   docker compose version
   ```

## Option 2: Install via Homebrew (If permissions are fixed)

If you fix the Homebrew permissions, you can use:

```bash
# Fix Homebrew permissions first
sudo chown -R $(whoami) /Users/sankar.amburkar/homebrew/Cellar

# Then install Docker Desktop
brew install --cask docker
```

## After Installation

Once Docker is installed, you can test it:

```bash
# Check Docker version
docker --version

# Check Docker Compose version
docker compose version

# Test with a simple container
docker run hello-world
```

## Start Your Microservices

After Docker is installed and running:

```bash
# Navigate to your project
cd /Users/sankar.amburkar/VSCode/finHealthMonitor

# Start all services
docker compose up

# Or run in background
docker compose up -d

# View logs
docker compose logs

# Stop services
docker compose down
```

## Troubleshooting

### Docker Desktop won't start
- Make sure you have enough disk space (at least 4GB free)
- Check System Preferences > Security & Privacy for any blocked permissions
- Restart your Mac if needed

### Permission denied errors
- Make sure Docker Desktop is running
- You may need to add your user to the docker group (usually automatic on macOS)

### Port already in use
- If port 8000 or 8001 is already in use, stop the existing service:
  ```bash
  # Find what's using the port
  lsof -i :8000
  lsof -i :8001
  
  # Kill the process if needed
  kill -9 <PID>
  ```
