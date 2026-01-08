/** @type {import('next').NextConfig} */
const nextConfig = {
  // Ensure environment variables are exposed
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
  // Log the API URL during build
  webpack: (config, { isServer }) => {
    if (isServer) {
      console.log('🔍 Build-time NEXT_PUBLIC_API_URL:', process.env.NEXT_PUBLIC_API_URL);
    }
    return config;
  },
}

module.exports = nextConfig
