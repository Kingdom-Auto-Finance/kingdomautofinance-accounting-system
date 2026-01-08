#!/bin/bash

# Startup script to run both Streamlit and FastAPI together
# This allows both UIs to coexist during the migration period

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

# Start Streamlit in the foreground
echo "Starting Streamlit UI on port 8080..."
cd /app
streamlit run ui.py --server.port=8080 --server.address=0.0.0.0

# If Streamlit exits, kill FastAPI too
echo "Streamlit exited, shutting down FastAPI..."
kill $FASTAPI_PID 2>/dev/null
