/**
 * Custom Next.js server with API proxy to FastAPI backend
 * This runs in production to proxy /api/* requests to localhost:8000
 */
const { createServer } = require('http');
const { parse } = require('url');
const next = require('next');
const httpProxy = require('http-proxy');

const dev = process.env.NODE_ENV !== 'production';
const hostname = process.env.HOSTNAME || '0.0.0.0';
const port = parseInt(process.env.PORT || '3000', 10);

// Initialize Next.js
const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

// Create proxy to FastAPI backend
const proxy = httpProxy.createProxyServer({
  target: 'http://localhost:8000',
  changeOrigin: true,
  ws: true, // Enable WebSocket proxying
});

// Handle proxy errors
proxy.on('error', (err, req, res) => {
  console.error('❌ Proxy error:', err.message);
  if (res.writeHead && !res.headersSent) {
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      error: 'Backend service unavailable',
      message: err.message
    }));
  }
});

app.prepare().then(() => {
  createServer(async (req, res) => {
    try {
      const parsedUrl = parse(req.url, true);
      const { pathname } = parsedUrl;

      // Proxy API requests to FastAPI backend
      if (pathname.startsWith('/api/') || pathname === '/health' || pathname === '/docs') {
        console.log(`🔄 Proxying: ${req.method} ${pathname} → http://localhost:8000`);
        proxy.web(req, res);
        return;
      }

      // Handle all other requests with Next.js
      await handle(req, res, parsedUrl);
    } catch (err) {
      console.error('❌ Server error:', err);
      res.statusCode = 500;
      res.end('Internal Server Error');
    }
  })
    .once('error', (err) => {
      console.error('❌ Server failed to start:', err);
      process.exit(1);
    })
    .listen(port, hostname, () => {
      console.log(`✅ Next.js server ready on http://${hostname}:${port}`);
      console.log(`🔌 Proxying /api/* requests to http://localhost:8000`);
    });
});
