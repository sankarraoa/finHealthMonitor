# Railway Environment Variables Checklist

Use this checklist when setting up your Railway services.

## Generated Secrets (Use These)

```
JWT_SECRET=WzbgyxavUnGjeCGqznwE3Kr0NeSxYYSK4smGZizrDEI
SECRET_KEY=q1EmPiyJX2YeCjbfo27he0gFsGniaK2VK8IZNxOG_3s
```

---

## User Service Environment Variables

**Service Name**: `user-service`  
**Root Directory**: `services/user-service`

| Variable | Value | Status |
|----------|-------|--------|
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` | ⬜ |
| `JWT_SECRET` | `WzbgyxavUnGjeCGqznwE3Kr0NeSxYYSK4smGZizrDEI` | ⬜ |
| `PORT` | `8001` | ⬜ |
| `USE_LOCAL_DB` | `false` | ⬜ |

---

## Gateway Service Environment Variables

**Service Name**: `gateway` (or your preferred name)  
**Root Directory**: `/` (root)

### Database & Infrastructure

| Variable | Value | Status |
|----------|-------|--------|
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` | ⬜ |
| `USE_LOCAL_DB` | `false` | ⬜ |
| `USER_SERVICE_URL` | `http://user-service.railway.internal:8001` | ⬜ |

### Security

| Variable | Value | Status |
|----------|-------|--------|
| `JWT_SECRET` | `WzbgyxavUnGjeCGqznwE3Kr0NeSxYYSK4smGZizrDEI` | ⬜ |
| `SECRET_KEY` | `q1EmPiyJX2YeCjbfo27he0gFsGniaK2VK8IZNxOG_3s` | ⬜ |

### Xero OAuth

| Variable | Value | Status |
|----------|-------|--------|
| `XERO_CLIENT_ID` | `<your_xero_client_id>` | ⬜ |
| `XERO_CLIENT_SECRET` | `<your_xero_client_secret>` | ⬜ |
| `XERO_REDIRECT_URI` | `https://your-gateway-url.up.railway.app/callback` | ⬜ |

**Note**: Replace `your-gateway-url` with your actual Railway domain after generating it.

### QuickBooks OAuth (Optional)

| Variable | Value | Status |
|----------|-------|--------|
| `QUICKBOOKS_CLIENT_ID` | `<your_quickbooks_client_id>` | ⬜ |
| `QUICKBOOKS_CLIENT_SECRET` | `<your_quickbooks_client_secret>` | ⬜ |
| `QUICKBOOKS_REDIRECT_URI` | `https://your-gateway-url.up.railway.app/quickbooks/callback` | ⬜ |
| `QUICKBOOKS_ENVIRONMENT` | `production` | ⬜ |

### LLM Provider - Toqan (Default)

| Variable | Value | Status |
|----------|-------|--------|
| `LLM_PROVIDER` | `toqan` | ⬜ |
| `TOQAN_API_KEY` | `<your_toqan_api_key>` | ⬜ |
| `TOQAN_API_BASE_URL` | `https://api.coco.prod.toqan.ai/api` | ⬜ |

### LLM Provider - OpenAI (Optional, for switching)

| Variable | Value | Status |
|----------|-------|--------|
| `OPENAI_API_KEY` | `<your_openai_api_key>` | ⬜ |
| `OPENAI_MODEL` | `gpt-4o` | ⬜ |

### Application Settings

| Variable | Value | Status |
|----------|-------|--------|
| `DEBUG` | `False` | ⬜ |
| `PORT` | `8000` | ⬜ |

---

## Quick Setup Steps

1. ✅ Create user-service in Railway
2. ✅ Set root directory to `services/user-service`
3. ✅ Add user-service environment variables
4. ✅ Create gateway service in Railway
5. ✅ Set root directory to `/` (root)
6. ✅ Generate gateway public URL
7. ✅ Add gateway environment variables (use gateway URL for redirect URIs)
8. ✅ Update Xero/QuickBooks developer portals with redirect URIs
9. ✅ Deploy and verify

---

## Important Notes

- **JWT_SECRET must be identical** in both user-service and gateway
- **USER_SERVICE_URL** must use Railway private networking format
- **DATABASE_URL** uses Railway's `${{ Postgres.DATABASE_URL }}` for private networking
- **OAuth redirect URIs** must match EXACTLY in developer portals
- **LLM_PROVIDER** defaults to Toqan if `TOQAN_API_KEY` is set

---

## Troubleshooting Provider Error

If you see "Provider Error" (error code 57):

1. **Check Railway Logs**:
   - Go to Gateway service → **Logs** tab
   - Look for LLM provider initialization messages
   - Check for Toqan API connection errors

2. **Verify Environment Variables**:
   - Ensure `TOQAN_API_KEY` is set correctly
   - Verify `LLM_PROVIDER=toqan` is set
   - Check that `TOQAN_API_BASE_URL` is correct

3. **Check Network Connectivity**:
   - Railway services have outbound internet access by default
   - Verify Toqan API is accessible: `https://api.coco.prod.toqan.ai/api`

4. **Test Toqan API Key**:
   - Verify your Toqan API key is valid
   - Check Toqan dashboard for API key status

5. **Fallback to OpenAI**:
   - If Toqan continues to fail, temporarily switch:
   - Set `LLM_PROVIDER=openai`
   - Ensure `OPENAI_API_KEY` is set
   - Redeploy

---

**Last Updated**: 2026-02-08
