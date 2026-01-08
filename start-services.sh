#!/bin/bash

echo "========================================="
echo "Kingdom Auto Finance v2.0"
echo "========================================="

# Start FastAPI backend
echo "Starting FastAPI on port 8000..."
cd /app
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!

# Wait for FastAPI to be ready
echo "Waiting for FastAPI to start..."
sleep 5

# Start Next.js frontend
echo "Starting Next.js on port 3000..."
cd /app/frontend/.next/standalone
PORT=3000 node server.js &
NEXTJS_PID=$!

echo "========================================="
echo "FastAPI running on port 8000 (PID: $FASTAPI_PID)"
echo "Next.js running on port 3000 (PID: $NEXTJS_PID)"
echo "========================================="

# Wait for both processes
wait $FASTAPI_PID $NEXTJS_PID
