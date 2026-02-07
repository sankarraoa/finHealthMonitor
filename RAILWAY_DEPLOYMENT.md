# Railway.app Deployment Guide

This guide will help you deploy FinHealthMonitor to Railway.app.

## Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **GitHub Account**: Railway works best with GitHub integration
3. **Xero Developer Account**: For OAuth credentials
4. **PostgreSQL Database**: Already set up on Railway (you have the connection string)

## Step 1: Prepare Your Repository

1. **Commit all changes** to your repository:
   ```bash
   git add .
   git commit -m "Prepare for Railway deployment"
   git push origin main
   ```

2. **Verify these files exist**:
   - `Dockerfile` ✅
   - `railway.json` ✅
   - `.dockerignore` ✅
   - `requirements.txt` ✅
   - `alembic.ini` ✅

## Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your `finHealthMonitor` repository
5. Railway will automatically detect the Dockerfile

## Step 3: Add PostgreSQL Database

1. In your Railway project, click **"+ New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway will create a PostgreSQL instance
4. **Note the connection string** (or use your existing one)

## Step 4: Configure Environment Variables

In your Railway project, go to **"Variables"** tab and add:

### Required Variables

```bash
# Database (use your existing Railway PostgreSQL connection string)
DATABASE_URL=postgresql://postgres:password@host:port/railway

# Xero OAuth
XERO_CLIENT_ID=your_xero_client_id
XERO_CLIENT_SECRET=your_xero_client_secret
XERO_REDIRECT_URI=https://your-app-name.up.railway.app/callback

# Session Security
SECRET_KEY=generate_a_random_32_char_string_here

# Application Settings
DEBUG=False
PORT=8000  # Railway sets this automatically, but good to have

# LLM Configuration (choose one)
LLM_PROVIDER=openai  # or "toqan"
OPENAI_API_KEY=your_openai_api_key  # if using OpenAI
# OR
TOQAN_API_KEY=your_toqan_api_key  # if using Toqan
TOQAN_API_BASE_URL=https://api.coco.prod.toqan.ai/api

# Optional: QuickBooks
QUICKBOOKS_CLIENT_ID=your_quickbooks_client_id  # if using QuickBooks
QUICKBOOKS_CLIENT_SECRET=your_quickbooks_client_secret
QUICKBOOKS_REDIRECT_URI=https://your-app-name.up.railway.app/callback/quickbooks
```

### Generate SECRET_KEY

Run this command to generate a secure secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Step 5: Update Xero Redirect URI

1. Go to [Xero Developer Portal](https://developer.xero.com/myapps)
2. Edit your app
3. Add your Railway URL to **Redirect URIs**:
   ```
   https://your-app-name.up.railway.app/callback
   ```
4. Save changes

## Step 6: Deploy

1. Railway will automatically start building when you push to GitHub
2. Or click **"Deploy"** in Railway dashboard
3. Watch the build logs for progress
4. Once deployed, Railway will provide a URL like:
   ```
   https://your-app-name.up.railway.app
   ```

## Step 7: Run Database Migrations

The Dockerfile includes `alembic upgrade head`, but if migrations fail:

1. Go to Railway project → **"Deployments"**
2. Click on the latest deployment
3. Open **"Logs"** to see if migrations ran
4. If needed, run manually:
   ```bash
   railway run alembic upgrade head
   ```

## Step 8: Verify Deployment

1. Visit your Railway URL
2. Test the connection flow
3. Check logs in Railway dashboard for any errors

## Troubleshooting

### Build Fails

**Error: "npm install failed"**
- Check that `xero-mcp-server` and `quickbooks-mcp-server` have valid `package.json`
- Ensure Node.js is installed in Dockerfile (already included)

**Error: "Database connection failed"**
- Verify `DATABASE_URL` is set correctly
- Check PostgreSQL service is running in Railway
- Test connection: `railway run python test_db_connection.py`

### Runtime Errors

**Error: "Module not found"**
- Check `requirements.txt` includes all dependencies
- Rebuild the container

**Error: "Port already in use"**
- Railway sets `PORT` automatically - don't hardcode port 8000
- The code now uses `os.getenv("PORT", 8000)`

**Error: "OAuth redirect mismatch"**
- Ensure `XERO_REDIRECT_URI` matches exactly what's in Xero Developer Portal
- Must use HTTPS (Railway provides this automatically)

### Database Issues

**Migrations not running**
- Check logs for Alembic errors
- Run manually: `railway run alembic upgrade head`
- Verify `DATABASE_URL` is accessible

## Railway-Specific Features

### Custom Domain

1. Go to **"Settings"** → **"Networking"**
2. Click **"Generate Domain"** or add custom domain
3. Update `XERO_REDIRECT_URI` to match new domain

### Environment Variables

- Railway automatically provides `PORT` and `RAILWAY_ENVIRONMENT`
- Use Railway's variable management for secrets
- Variables are encrypted at rest

### Scaling

- Railway free tier: 1 instance
- Upgrade for multiple instances (requires shared cache/Redis)
- Current setup supports single instance well

### Monitoring

- View logs in Railway dashboard
- Set up alerts for deployment failures
- Monitor resource usage

## Post-Deployment Checklist

- [ ] Application is accessible at Railway URL
- [ ] Database migrations completed successfully
- [ ] Xero OAuth flow works (connect button)
- [ ] Can view connections in settings
- [ ] Can run payroll risk analysis
- [ ] Logs show no critical errors
- [ ] Environment variables are set correctly

## Cost Estimation

**Railway Free Tier:**
- $5/month credit
- PostgreSQL: ~$5/month (free tier available)
- App hosting: ~$5/month for small apps
- **Total: ~$5-10/month** (within free tier for small usage)

**For 1000 connections:**
- Consider upgrading to Pro plan ($20/month)
- Add Redis for shared cache ($5/month)
- Monitor database usage (may need upgrade)

## Next Steps

1. **Set up monitoring**: Use Railway's built-in monitoring
2. **Add Redis** (optional): For shared cache across instances
3. **Custom domain**: Add your own domain name
4. **Backup strategy**: Railway handles PostgreSQL backups automatically
5. **CI/CD**: Railway auto-deploys on git push (already configured)

## Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Check Railway dashboard logs for detailed error messages
