#!/bin/bash

# Startup script to run FastAPI backend and Next.js frontend

echo "Starting Kingdom Auto Finance Accounting System..."
echo "=================================================="

# Start FastAPI in the background
echo "Starting FastAPI backend on port 8000..."
cd /app/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!
echo "FastAPI started with PID: $FASTAPI_PID"

# Wait a moment for FastAPI to start
sleep 2

# Start Next.js with custom proxy server in the foreground
echo "Starting Next.js frontend with API proxy on port 3000..."
cd /app/nextjs
node server-with-proxy.js &
NEXTJS_PID=$!
echo "Next.js started with PID: $NEXTJS_PID"

# Wait for both processes
wait $FASTAPI_PID $NEXTJS_PID
