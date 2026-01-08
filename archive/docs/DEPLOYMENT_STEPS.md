# Deployment Steps - Kingdom Auto Finance v2.0

## What We Just Did

Updated your system to run both FastAPI backend and Next.js frontend in a single container.

## Files Created/Updated

1. **Dockerfile** - Now builds both Python backend and Next.js frontend
2. **start-services.sh** - Startup script that runs both services
3. **.dockerignore** - Optimizes Docker build

## Deployment Process

### Step 1: Commit and Push to GitHub

```bash
git add .
git commit -m "Deploy Next.js frontend with FastAPI backend

- Updated Dockerfile to install Node.js and build Next.js
- Created start-services.sh to run both services
- Exposed ports 3000 (Next.js) and 8000 (FastAPI)
- Added .dockerignore for optimized builds

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
git push origin main
```

### Step 2: DigitalOcean Will Automatically Rebuild

Once you push to GitHub, DigitalOcean will:
1. Pull the new code
2. Build the Docker image with the new Dockerfile
3. Install Node.js during build
4. Build the Next.js app during build
5. Start the container with both services running

### Step 3: Update Port Configuration

After deployment, you need to expose port 3000 (Next.js frontend) to the internet.

**Your current setup likely exposes port 8080 (old Streamlit). You need to:**

1. Update your DigitalOcean service/ingress to expose port **3000** instead
2. Or add port 3000 alongside your existing configuration

### Step 4: Access Your New Application

Once deployed:
- **Frontend (Users)**: `http://your-domain:3000` (or your configured URL)
- **API (Direct)**: `http://your-domain:8000` (optional, for debugging)

## Environment Variables

Make sure these environment variables are set in your DigitalOcean configuration:

```bash
# Backend (existing)
SUPABASE_URL=https://puwcyhbjchkfvvaccacg.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-actual-key
GOOGLE_CREDENTIALS_JSON=your-credentials

# Frontend (new - optional, has defaults)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Note:** If both services run in the same container, `NEXT_PUBLIC_API_URL=http://localhost:8000` is correct.

## Login Credentials

- **Password**: `Kingdom2025!$$` (same as before)

## Verification Checklist

After deployment, test:

- [ ] Visit frontend at port 3000
- [ ] Login with password
- [ ] Dashboard loads
- [ ] Fetch payments (watch progress bar)
- [ ] Process payments (watch progress bar)
- [ ] Generate reports
- [ ] Download CSV files
- [ ] Import amortization schedules

## Troubleshooting

### Container won't start
- Check DigitalOcean logs for build errors
- Verify all files committed to GitHub
- Check that `start-services.sh` has execute permissions

### Frontend shows "Connection Error"
- Verify `NEXT_PUBLIC_API_URL` points to correct backend URL
- Check that both services are running (logs should show both PIDs)

### Build takes too long
- This is normal on first build (installing Node.js + npm packages)
- Subsequent builds will be faster due to Docker layer caching

## Rollback Plan

If something goes wrong:

```bash
git revert HEAD
git push origin main
```

This will revert to your previous Streamlit setup.

## Next Steps

Once verified working:
1. Update DNS to point to new frontend (port 3000)
2. Test all features thoroughly
3. Remove old Streamlit code (optional)
4. Phase 3: Add multi-user, charts, advanced features

---

**Questions?** Check the logs in your DigitalOcean dashboard or container terminal.
