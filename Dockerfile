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

# Build Next.js frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
ENV npm_config_cache=/tmp/.npm
RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm config set prefer-offline true \
    && npm config set audit false \
    && npm install
COPY frontend/ ./
RUN npm run build

# Copy Next.js standalone build files
RUN cp -r .next/standalone/. /app/nextjs/ && \
    cp -r .next/static /app/nextjs/.next/static && \
    ([ -d public ] && cp -r public /app/nextjs/public || true)

# Back to root
WORKDIR /app

# Copy startup script
COPY start.sh ./
RUN chmod +x start.sh

# Environment variables
ENV NEXT_PUBLIC_API_URL=http://localhost:8000
ENV PYTHONPATH=/app

EXPOSE 3000 8000

CMD ["./start.sh"]
