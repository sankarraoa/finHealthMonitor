# Gateway Service Variables - Missing & Fixes

## ❌ CRITICAL: Missing Variables

### 1. USER_SERVICE_URL (REQUIRED)
**Status**: ❌ MISSING  
**Add this**:
```
USER_SERVICE_URL=http://user-service.railway.internal:8001
```

**Why**: The gateway needs to communicate with the user-service. Without this, authentication will fail.

---

## ⚠️ Variables That Need Updating

### 2. XERO_REDIRECT_URI (WRONG VALUE)
**Current**: `http://localhost:8000/callback`  
**Should be**: `https://your-gateway-url.up.railway.app/callback`

**Steps to fix**:
1. Go to your Gateway service in Railway
2. Click **Settings** → **Networking**
3. Copy your Railway domain (e.g., `https://gateway-production.up.railway.app`)
4. Update `XERO_REDIRECT_URI` to: `https://your-actual-domain.up.railway.app/callback`
5. Also update this in Xero Developer Portal: [developer.xero.com/myapps](https://developer.xero.com/myapps)

---

## 🗑️ Variables to Remove (Not Needed)

These variables are not needed in Railway and can cause confusion:

1. **LOCAL_DATABASE_URL** - Remove this (only for local development)
2. **RAILWAY_DATABASE_URL** - Remove this (use `DATABASE_URL` with `${{Postgres.DATABASE_URL}}` instead)

---

## ✅ Complete Gateway Variables List

Here's your complete, corrected list:

```env
# Database
DATABASE_URL=${{Postgres.DATABASE_URL}}
USE_LOCAL_DB=false

# Microservices Communication (ADD THIS!)
USER_SERVICE_URL=http://user-service.railway.internal:8001

# Security (⚠️ Generate new secrets for production!)
JWT_SECRET=<your_jwt_secret>
SECRET_KEY=<your_secret_key>

# Xero OAuth
XERO_CLIENT_ID=<your_xero_client_id>
XERO_CLIENT_SECRET=<your_xero_client_secret>
XERO_REDIRECT_URI=https://your-gateway-url.up.railway.app/callback

# LLM Provider - Toqan
LLM_PROVIDER=toqan
TOQAN_API_KEY=<your_toqan_api_key>
TOQAN_API_BASE_URL=https://api.coco.prod.toqan.ai/api

# LLM Provider - OpenAI (for switching)
OPENAI_API_KEY=<your_openai_api_key>
OPENAI_MODEL=gpt-4o

# Application Settings
DEBUG=False
PORT=8000
```

---

## 📋 Action Items

1. ✅ **Add** `USER_SERVICE_URL=http://user-service.railway.internal:8001`
2. ✅ **Update** `XERO_REDIRECT_URI` to your Railway gateway URL
3. ✅ **Remove** `LOCAL_DATABASE_URL` (if present)
4. ✅ **Remove** `RAILWAY_DATABASE_URL` (if present)
5. ✅ **Update** Xero Developer Portal with the new redirect URI

---

## 🔍 How to Find Your Railway Gateway URL

1. Go to Railway dashboard
2. Click on your **Gateway** service
3. Go to **Settings** → **Networking**
4. Click **"Generate Domain"** (if not already generated)
5. Copy the URL (e.g., `https://gateway-production.up.railway.app`)
6. Use this URL in `XERO_REDIRECT_URI`

---

## ⚠️ Important Notes

- **USER_SERVICE_URL** must use Railway's private networking format: `http://user-service.railway.internal:8001`
- **XERO_REDIRECT_URI** must use HTTPS (Railway provides this automatically)
- The redirect URI in Xero Developer Portal must match **EXACTLY** (including `https://` and `/callback`)
