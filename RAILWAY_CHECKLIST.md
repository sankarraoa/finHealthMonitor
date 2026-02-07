# Railway Deployment Checklist

## Quick Reference

### Files Created ✅
- [x] `Dockerfile` - Container configuration
- [x] `.dockerignore` - Exclude unnecessary files
- [x] `railway.json` - Railway deployment config
- [x] `start.sh` - Startup script (runs migrations + starts app)
- [x] `RAILWAY_DEPLOYMENT.md` - Full deployment guide

### Code Changes ✅
- [x] Updated `app/main.py` to use `PORT` environment variable
- [x] Startup script runs database migrations automatically

## Required Information for Railway

### 1. Database Connection String
You already have this:
```
DATABASE_URL=postgresql://postgres:nIrSLrxNUhzPghZJiuKVwGwcFMxiAzgh@metro.proxy.rlwy.net:10176/railway
```

### 2. Xero OAuth Credentials
Get from: https://developer.xero.com/myapps
- `XERO_CLIENT_ID` - Your Xero app client ID
- `XERO_CLIENT_SECRET` - Your Xero app client secret
- `XERO_REDIRECT_URI` - Will be: `https://your-app-name.up.railway.app/callback`

### 3. Security
- `SECRET_KEY` - Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### 4. LLM Provider (Choose One)
**Option A: OpenAI**
- `LLM_PROVIDER=openai`
- `OPENAI_API_KEY` - Your OpenAI API key

**Option B: Toqan**
- `LLM_PROVIDER=toqan`
- `TOQAN_API_KEY` - Your Toqan API key
- `TOQAN_API_BASE_URL=https://api.coco.prod.toqan.ai/api`

### 5. Application Settings
- `DEBUG=False` (for production)
- `PORT=8000` (Railway sets this automatically, but good to have)

### 6. Optional: QuickBooks
- `QUICKBOOKS_CLIENT_ID` - If using QuickBooks
- `QUICKBOOKS_CLIENT_SECRET` - If using QuickBooks
- `QUICKBOOKS_REDIRECT_URI` - `https://your-app-name.up.railway.app/callback/quickbooks`

## Deployment Steps

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Add Railway deployment configuration"
   git push origin main
   ```

2. **Create Railway Project**
   - Go to railway.app
   - New Project → Deploy from GitHub
   - Select your repository

3. **Add PostgreSQL** (if not already added)
   - New → Database → PostgreSQL
   - Copy connection string

4. **Set Environment Variables**
   - Go to Variables tab
   - Add all variables from section above
   - **Important**: Update `XERO_REDIRECT_URI` after Railway gives you the URL

5. **Update Xero Redirect URI**
   - Go to Xero Developer Portal
   - Edit your app
   - Add Railway URL: `https://your-app-name.up.railway.app/callback`

6. **Deploy**
   - Railway auto-deploys on git push
   - Or click "Deploy" button
   - Watch logs for progress

7. **Verify**
   - Visit Railway URL
   - Test OAuth flow
   - Check logs for errors

## Common Issues

### Build Fails
- Check Dockerfile syntax
- Verify Node.js MCP servers build correctly
- Check logs for specific error

### Database Connection Fails
- Verify `DATABASE_URL` is correct
- Check PostgreSQL service is running
- Test: `railway run python test_db_connection.py`

### OAuth Redirect Mismatch
- `XERO_REDIRECT_URI` must match exactly
- Must use HTTPS (Railway provides this)
- No trailing slashes

### Migrations Fail
- Check `DATABASE_URL` is accessible
- Run manually: `railway run alembic upgrade head`
- Check logs for Alembic errors

## Railway URL Format

After deployment, your app will be at:
```
https://your-app-name.up.railway.app
```

Railway auto-generates the name, or you can set a custom domain.

## Cost

- **Free Tier**: $5/month credit
- **PostgreSQL**: ~$5/month (or free tier)
- **App Hosting**: ~$5/month for small apps
- **Total**: Usually within free tier for small usage

For 1000 connections, consider Pro plan ($20/month).

## Next Steps After Deployment

1. Test all features
2. Set up monitoring
3. Configure custom domain (optional)
4. Set up backups (Railway handles this)
5. Monitor resource usage
