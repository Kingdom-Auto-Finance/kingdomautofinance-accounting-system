FROM python:3.11-slim

WORKDIR /app

# Install Node.js 18.x
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
COPY backend/requirements.txt ./backend-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r backend-requirements.txt

# Copy Python code
COPY src/ ./src/
COPY backend/ ./backend/
COPY *.py ./

# Build Next.js frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Back to root
WORKDIR /app

# Copy startup script
COPY start-services.sh ./
RUN chmod +x start-services.sh

# Environment variables
ENV NEXT_PUBLIC_API_URL=http://localhost:8000
ENV PYTHONPATH=/app

EXPOSE 3000 8000

CMD ["./start-services.sh"]
