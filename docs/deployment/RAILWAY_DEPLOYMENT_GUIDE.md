# Railway Deployment Guide - FinHealthMonitor Microservices

This guide will help you deploy FinHealthMonitor to Railway.app with microservices architecture.

## Prerequisites

- ✅ Railway account: [railway.app](https://railway.app)
- ✅ GitHub repository: `https://github.com/sankarraoa/finHealthMonitor` (main branch)
- ✅ Railway project "getGo" already created and connected to GitHub
- ✅ PostgreSQL database already deployed in Railway project

## Generated Secrets

**IMPORTANT**: Use these generated secrets for production:

```
JWT_SECRET=WzbgyxavUnGjeCGqznwE3Kr0NeSxYYSK4smGZizrDEI
SECRET_KEY=q1EmPiyJX2YeCjbfo27he0gFsGniaK2VK8IZNxOG_3s
```

**Both services must use the SAME `JWT_SECRET`** for authentication to work.

---

## Step 1: Deploy User Service

### 1.1 Create User Service

1. Go to your Railway project "getGo"
2. Click **"+ New"** → **"GitHub Repo"**
3. Select `sankarraoa/finHealthMonitor`
4. Railway will create a new service

### 1.2 Configure User Service

1. **Set Root Directory**:
   - Click on the service → **Settings** → **Source**
   - Set **Root Directory** to: `services/user-service`
   - Railway will auto-detect the Dockerfile

2. **Connect to PostgreSQL**:
   - Go to **Variables** tab
   - Click **"+ New Variable"**
   - Add: `DATABASE_URL` = `${{ Postgres.DATABASE_URL }}`
   - This uses Railway's private networking

3. **Set Environment Variables**:
   Add these variables in the **Variables** tab:

   ```env
   DATABASE_URL=${{ Postgres.DATABASE_URL }}
   JWT_SECRET=WzbgyxavUnGjeCGqznwE3Kr0NeSxYYSK4smGZizrDEI
   PORT=8001
   USE_LOCAL_DB=false
   ```

4. **Generate Public URL** (optional, for testing):
   - Go to **Settings** → **Networking**
   - Click **"Generate Domain"**
   - Note the URL (e.g., `https://user-service-production.up.railway.app`)

### 1.3 Verify User Service Deployment

1. Check **Deployments** tab for build status
2. Once deployed, check **Logs** tab
3. Look for: `"Starting user-service..."` and `"Application startup complete"`
4. Test health endpoint: `https://your-user-service-url.up.railway.app/health`

---

## Step 2: Deploy Gateway Service

### 2.1 Create Gateway Service

1. In the same Railway project "getGo"
2. Click **"+ New"** → **"GitHub Repo"**
3. Select `sankarraoa/finHealthMonitor` again
4. Railway will create another service

### 2.2 Configure Gateway Service

1. **Set Root Directory**:
   - Click on the service → **Settings** → **Source**
   - Set **Root Directory** to: `/` (root - default)
   - Railway will auto-detect the Dockerfile

2. **Connect to PostgreSQL**:
   - Go to **Variables** tab
   - Add: `DATABASE_URL` = `${{ Postgres.DATABASE_URL }}`

3. **Set Environment Variables**:
   Add ALL these variables in the **Variables** tab:

   ```env
   # Database
   DATABASE_URL=${{ Postgres.DATABASE_URL }}
   USE_LOCAL_DB=false

   # Microservices Communication
   USER_SERVICE_URL=http://user-service.railway.internal:8001
   
   # Security (MUST match user-service JWT_SECRET)
   JWT_SECRET=WzbgyxavUnGjeCGqznwE3Kr0NeSxYYSK4smGZizrDEI
   SECRET_KEY=q1EmPiyJX2YeCjbfo27he0gFsGniaK2VK8IZNxOG_3s

   # Xero OAuth (REPLACE WITH YOUR VALUES)
   XERO_CLIENT_ID=<your_xero_client_id>
   XERO_CLIENT_SECRET=<your_xero_client_secret>
   XERO_REDIRECT_URI=https://your-gateway-url.up.railway.app/callback

   # QuickBooks OAuth (REPLACE WITH YOUR VALUES - optional)
   QUICKBOOKS_CLIENT_ID=<your_quickbooks_client_id>
   QUICKBOOKS_CLIENT_SECRET=<your_quickbooks_client_secret>
   QUICKBOOKS_REDIRECT_URI=https://your-gateway-url.up.railway.app/quickbooks/callback
   QUICKBOOKS_ENVIRONMENT=production

   # LLM Provider - Toqan (default)
   LLM_PROVIDER=toqan
   TOQAN_API_KEY=<your_toqan_api_key>
   TOQAN_API_BASE_URL=https://api.coco.prod.toqan.ai/api

   # LLM Provider - OpenAI (for switching/fallback)
   OPENAI_API_KEY=<your_openai_api_key>
   OPENAI_MODEL=gpt-4o

   # Application Settings
   DEBUG=False
   PORT=8000
   ```

4. **Generate Public URL**:
   - Go to **Settings** → **Networking**
   - Click **"Generate Domain"**
   - **IMPORTANT**: Copy this URL - you'll need it for OAuth redirect URIs
   - Example: `https://gateway-production.up.railway.app`

### 2.3 Update OAuth Redirect URIs

After you get your gateway URL, update these in their respective developer portals:

**Xero Developer Portal** ([developer.xero.com/myapps](https://developer.xero.com/myapps)):
- Add redirect URI: `https://your-gateway-url.up.railway.app/callback`
- Update `XERO_REDIRECT_URI` in Railway to match exactly

**QuickBooks Developer Portal** ([developer.intuit.com](https://developer.intuit.com)):
- Add redirect URI: `https://your-gateway-url.up.railway.app/quickbooks/callback`
- Update `QUICKBOOKS_REDIRECT_URI` in Railway to match exactly

### 2.4 Verify Gateway Deployment

1. Check **Deployments** tab for build status
2. Watch **Logs** tab during deployment
3. Look for:
   - `"FinHealthMonitor Starting Up"`
   - `"LLM Provider: toqan"`
   - `"✅ Using Toqan LLM Engine"`
   - `"Application startup complete"`
4. Test the app: Visit `https://your-gateway-url.up.railway.app`

---

## Step 3: Verify Deployment

### 3.1 Check Service Health

**User Service**:
```bash
curl https://your-user-service-url.up.railway.app/health
# Should return: {"status":"healthy","service":"user-service","version":"1.0.0"}
```

**Gateway**:
```bash
curl https://your-gateway-url.up.railway.app/
# Should redirect to login page
```

### 3.2 Check Logs

In Railway, check logs for both services:

**User Service logs should show**:
- Database migrations running
- `"Starting user-service..."`
- `"Application startup complete"`

**Gateway logs should show**:
- Database migrations running
- `"FinHealthMonitor Starting Up"`
- `"LLM Provider: toqan"`
- `"✅ Using Toqan LLM Engine"`
- MCP servers cloning and building (Xero and QuickBooks)
- `"Application startup complete"`

### 3.3 Test Authentication Flow

1. Visit your gateway URL
2. Click "Login" or "Connect with Xero"
3. Complete OAuth flow
4. Verify you're redirected back successfully

---

## Troubleshooting

### Issue: "Cannot connect to user-service"

**Solution**: 
- Verify `USER_SERVICE_URL` uses Railway private networking: `http://user-service.railway.internal:8001`
- Check that both services are in the same Railway project
- Verify `JWT_SECRET` matches in both services

### Issue: "MCP server clone failed"

**Solution**:
- Check Railway build logs for git clone errors
- Verify GitHub repos are public:
  - `https://github.com/XeroAPI/xero-mcp-server`
  - `https://github.com/intuit/quickbooks-online-mcp-server`
- The build will continue even if QuickBooks clone fails (it's optional)

### Issue: "Database connection failed"

**Solution**:
- Verify `DATABASE_URL=${{ Postgres.DATABASE_URL }}` is set correctly
- Check that PostgreSQL service is running in Railway
- Verify both services use the same database reference

### Issue: "Provider Error" (Toqan/OpenAI)

**Solution**:
- Check that `TOQAN_API_KEY` is set correctly in gateway service
- Verify `LLM_PROVIDER=toqan` is set
- Check Railway logs for API connection errors
- Verify network connectivity (Railway should have outbound internet access)

### Issue: "401 Unauthorized" from OpenAI

**Solution**:
- This means OpenAI is being used instead of Toqan
- Check logs for `"LLM Provider: ..."` to see which provider is active
- Verify `TOQAN_API_KEY` is set and `LLM_PROVIDER=toqan`
- If you want OpenAI, set `LLM_PROVIDER=openai` and ensure `OPENAI_API_KEY` is set

### Issue: OAuth redirect mismatch

**Solution**:
- Ensure redirect URIs in Xero/QuickBooks portals match EXACTLY
- Must use HTTPS (Railway provides this automatically)
- Check Railway logs for OAuth callback errors

---

## Environment Variables Reference

### User Service Variables

| Variable | Value | Required |
|----------|-------|----------|
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` | ✅ Yes |
| `JWT_SECRET` | `WzbgyxavUnGjeCGqznwE3Kr0NeSxYYSK4smGZizrDEI` | ✅ Yes |
| `PORT` | `8001` | ✅ Yes |
| `USE_LOCAL_DB` | `false` | ✅ Yes |

### Gateway Service Variables

| Variable | Value | Required |
|----------|-------|----------|
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` | ✅ Yes |
| `USER_SERVICE_URL` | `http://user-service.railway.internal:8001` | ✅ Yes |
| `JWT_SECRET` | `WzbgyxavUnGjeCGqznwE3Kr0NeSxYYSK4smGZizrDEI` | ✅ Yes |
| `SECRET_KEY` | `q1EmPiyJX2YeCjbfo27he0gFsGniaK2VK8IZNxOG_3s` | ✅ Yes |
| `XERO_CLIENT_ID` | Your Xero Client ID | ✅ Yes |
| `XERO_CLIENT_SECRET` | Your Xero Client Secret | ✅ Yes |
| `XERO_REDIRECT_URI` | `https://your-gateway-url.up.railway.app/callback` | ✅ Yes |
| `QUICKBOOKS_CLIENT_ID` | Your QuickBooks Client ID | ⚠️ Optional |
| `QUICKBOOKS_CLIENT_SECRET` | Your QuickBooks Client Secret | ⚠️ Optional |
| `QUICKBOOKS_REDIRECT_URI` | `https://your-gateway-url.up.railway.app/quickbooks/callback` | ⚠️ Optional |
| `LLM_PROVIDER` | `toqan` | ✅ Yes |
| `TOQAN_API_KEY` | Your Toqan API Key | ✅ Yes |
| `TOQAN_API_BASE_URL` | `https://api.coco.prod.toqan.ai/api` | ✅ Yes |
| `OPENAI_API_KEY` | Your OpenAI API Key | ⚠️ Optional |
| `OPENAI_MODEL` | `gpt-4o` | ⚠️ Optional |
| `DEBUG` | `False` | ✅ Yes |
| `PORT` | `8000` | ✅ Yes |
| `USE_LOCAL_DB` | `false` | ✅ Yes |

---

## Switching LLM Providers

To switch from Toqan to OpenAI:

1. Go to Gateway service → **Variables**
2. Change `LLM_PROVIDER` from `toqan` to `openai`
3. Ensure `OPENAI_API_KEY` is set
4. Railway will automatically redeploy

To switch back to Toqan:

1. Change `LLM_PROVIDER` back to `toqan`
2. Or remove `LLM_PROVIDER` entirely (auto-detects Toqan if `TOQAN_API_KEY` is set)

---

## Next Steps

1. ✅ Deploy user-service
2. ✅ Deploy gateway
3. ✅ Update OAuth redirect URIs
4. ✅ Test authentication
5. ✅ Test payroll risk analysis
6. ✅ Monitor logs for any issues

---

## Support

If you encounter issues:
1. Check Railway logs for both services
2. Verify all environment variables are set correctly
3. Check that services can communicate (private networking)
4. Verify database connectivity
5. Check OAuth redirect URIs match exactly

---

**Last Updated**: 2026-02-08
**Railway Project**: getGo
**GitHub Repo**: https://github.com/sankarraoa/finHealthMonitor
