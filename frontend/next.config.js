/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Ensure environment variables are exposed
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
  // Proxy API requests to FastAPI backend
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
      {
        source: '/health',
        destination: 'http://localhost:8000/health',
      },
      {
        source: '/docs',
        destination: 'http://localhost:8000/docs',
      },
    ];
  },
  // Log the API URL during build
  webpack: (config, { isServer }) => {
    if (isServer) {
      console.log('🔍 Build-time NEXT_PUBLIC_API_URL:', process.env.NEXT_PUBLIC_API_URL);
      console.log('🔍 Build mode: standalone');
    }
    return config;
  },
}

module.exports = nextConfig
