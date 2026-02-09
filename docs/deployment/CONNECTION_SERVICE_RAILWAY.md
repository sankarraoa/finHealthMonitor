# Connection Service - Railway Deployment Guide

This guide will help you deploy the Connection Service microservice to Railway.app.

## Prerequisites

- ✅ Railway account: [railway.app](https://railway.app)
- ✅ Railway project "getGo" already created
- ✅ PostgreSQL database already deployed in Railway project
- ✅ User Service already deployed (for reference)

---

## Step 1: Create Connection Service

### 1.1 Add New Service

1. Go to your Railway project "getGo"
2. Click **"+ New"** → **"GitHub Repo"**
3. Select `sankarraoa/finHealthMonitor`
4. Railway will create a new service

### 1.2 Configure Service Settings

1. **Rename the Service** (optional but recommended):
   - Click on the service name at the top
   - Rename to: `connection-service`

2. **Set Root Directory**:
   - Click on the service → **Settings** → **Source**
   - Set **Root Directory** to: `services/connection-service`
   - Railway will auto-detect the `Dockerfile` and `railway.json`

---

## Step 2: Configure Environment Variables

### 2.1 Database Connection

1. Go to **Variables** tab
2. Click **"+ New Variable"**
3. Add:
   ```
   DATABASE_URL=${{ Postgres.DATABASE_URL }}
   ```
   This uses Railway's private networking to connect to your PostgreSQL database.

### 2.2 Service Configuration

Add these required variables:

```env
# Database
DATABASE_URL=${{ Postgres.DATABASE_URL }}
USE_LOCAL_DB=false
PORT=8002
```

### 2.3 Xero OAuth Configuration

Add your Xero OAuth credentials:

```env
# Xero OAuth
XERO_CLIENT_ID=<your_xero_client_id>
XERO_CLIENT_SECRET=<your_xero_client_secret>
XERO_REDIRECT_URI=https://your-gateway-url.up.railway.app/callback
```

**Important**: 
- Replace `<your_xero_client_id>` and `<your_xero_client_secret>` with your actual Xero credentials
- The `XERO_REDIRECT_URI` should point to your **Gateway service** URL (not the connection service)
- This URI must match exactly what's configured in Xero Developer Portal

### 2.4 QuickBooks OAuth Configuration (Optional)

If you're using QuickBooks:

```env
# QuickBooks OAuth
QUICKBOOKS_CLIENT_ID=<your_quickbooks_client_id>
QUICKBOOKS_CLIENT_SECRET=<your_quickbooks_client_secret>
QUICKBOOKS_REDIRECT_URI=https://your-gateway-url.up.railway.app/quickbooks/callback
QUICKBOOKS_ENVIRONMENT=production
```

**Note**: 
- For sandbox testing, set `QUICKBOOKS_ENVIRONMENT=sandbox`
- For production, set `QUICKBOOKS_ENVIRONMENT=production`

### 2.5 Complete Environment Variables List

Here's the complete list of variables to add:

```env
# Database
DATABASE_URL=${{ Postgres.DATABASE_URL }}
USE_LOCAL_DB=false
PORT=8002

# Xero OAuth (REQUIRED)
XERO_CLIENT_ID=<your_xero_client_id>
XERO_CLIENT_SECRET=<your_xero_client_secret>
XERO_REDIRECT_URI=https://your-gateway-url.up.railway.app/callback

# QuickBooks OAuth (OPTIONAL)
QUICKBOOKS_CLIENT_ID=<your_quickbooks_client_id>
QUICKBOOKS_CLIENT_SECRET=<your_quickbooks_client_secret>
QUICKBOOKS_REDIRECT_URI=https://your-gateway-url.up.railway.app/quickbooks/callback
QUICKBOOKS_ENVIRONMENT=production

# Application Settings
DEBUG=False
```

---

## Step 3: Deploy

### 3.1 Trigger Deployment

1. Railway will automatically detect changes and start building
2. Go to **Deployments** tab to monitor the build
3. Wait for the build to complete (usually 2-5 minutes)

### 3.2 Monitor Build Logs

1. Click on the active deployment
2. Check the build logs for any errors
3. Look for:
   - ✅ `Building Docker image...`
   - ✅ `Running database migrations...`
   - ✅ `Starting connection-service...`
   - ✅ `Application startup complete`

### 3.3 Common Build Issues

**Issue**: "Module not found" errors
- **Solution**: Ensure `Root Directory` is set to `services/connection-service`

**Issue**: "Database connection failed"
- **Solution**: Verify `DATABASE_URL` is set to `${{ Postgres.DATABASE_URL }}`

**Issue**: "Port already in use"
- **Solution**: Ensure `PORT=8002` is set (different from user-service which uses 8001)

---

## Step 4: Verify Deployment

### 4.1 Check Health Endpoint

1. Go to **Settings** → **Networking**
2. Click **"Generate Domain"** (if not already generated)
3. Note the URL (e.g., `https://connection-service-production.up.railway.app`)
4. Test the health endpoint:
   ```bash
   curl https://your-connection-service-url.up.railway.app/health
   ```
   
   Expected response:
   ```json
   {
     "status": "healthy",
     "service": "connection-service",
     "version": "1.0.0"
   }
   ```

### 4.2 Check Service Logs

1. Go to **Logs** tab
2. Look for:
   - `Starting connection-service...`
   - `Database initialized successfully`
   - `Application startup complete`
   - No error messages

### 4.3 Test API Endpoints

Test the root endpoint:
```bash
curl https://your-connection-service-url.up.railway.app/
```

Expected response:
```json
{
  "service": "connection-service",
  "version": "1.0.0",
  "status": "running"
}
```

---

## Step 5: Update Gateway Service

After deploying the connection service, update your Gateway service to use it:

### 5.1 Add Connection Service URL

1. Go to your **Gateway** service in Railway
2. Go to **Variables** tab
3. Add or update:
   ```
   CONNECTION_SERVICE_URL=http://connection-service.railway.internal:8002
   ```

**Important**: Use Railway's internal networking format (`railway.internal`) for service-to-service communication.

### 5.2 Verify Gateway Can Reach Connection Service

The gateway should now be able to proxy connection-related requests to the connection service.

---

## Step 6: Update OAuth Redirect URIs

### 6.1 Xero Developer Portal

1. Go to [Xero Developer Portal](https://developer.xero.com/myapps)
2. Select your app
3. Go to **OAuth 2.0 redirect URIs**
4. Ensure the redirect URI matches your Gateway URL:
   ```
   https://your-gateway-url.up.railway.app/callback
   ```
5. **Important**: Do NOT include the port number (Railway handles this automatically)

### 6.2 QuickBooks Developer Portal (if using)

1. Go to [QuickBooks Developer Portal](https://developer.intuit.com/)
2. Update redirect URIs to match your Gateway URL:
   ```
   https://your-gateway-url.up.railway.app/quickbooks/callback
   ```

---

## Troubleshooting

### Service Won't Start

**Check logs for**:
- Database connection errors → Verify `DATABASE_URL`
- Port conflicts → Ensure `PORT=8002`
- Missing dependencies → Check build logs

### OAuth Not Working

**Check**:
- `XERO_REDIRECT_URI` matches Xero Developer Portal exactly
- Gateway service has `CONNECTION_SERVICE_URL` set
- OAuth credentials are correct

### Database Migration Errors

**Solution**:
- The service will continue even if migrations fail (tables may already exist)
- Check logs for specific migration errors
- If needed, manually run migrations in Railway's database console

---

## Service Architecture

```
┌─────────────┐
│   Gateway   │ (Port 8000)
│   Service   │
└──────┬──────┘
       │
       ├──→ http://user-service.railway.internal:8001
       │
       └──→ http://connection-service.railway.internal:8002
                    │
                    └──→ PostgreSQL Database
```

---

## Next Steps

1. ✅ Connection Service deployed
2. ✅ Gateway updated with `CONNECTION_SERVICE_URL`
3. ✅ OAuth redirect URIs configured
4. 🔄 Test OAuth flow through Gateway
5. 🔄 Verify connections can be created/refreshed

---

## Quick Reference

**Service URL Format**:
- Public: `https://connection-service-production.up.railway.app`
- Internal: `http://connection-service.railway.internal:8002`

**Key Endpoints**:
- Health: `/health`
- Root: `/`
- API: `/api/connections/*`

**Port**: `8002` (different from user-service which uses `8001`)
