#!/usr/bin/env node

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

console.log('\n🔍 Environment Variable Validation');
console.log('=====================================');
console.log('NEXT_PUBLIC_API_URL:', apiUrl || 'NOT SET ❌');

if (!apiUrl) {
  console.error('\n❌ ERROR: NEXT_PUBLIC_API_URL is not set!');
  console.error('\nIn DigitalOcean App Platform:');
  console.error('1. Go to Settings → App-Level Environment Variables');
  console.error('2. Add: NEXT_PUBLIC_API_URL = https://amortization-system-j2db5.ondigitalocean.app');
  console.error('3. Make sure "Encrypt" is OFF');
  console.error('4. Save and redeploy\n');
  process.exit(1);
}

if (!apiUrl.startsWith('http')) {
  console.error('\n❌ ERROR: NEXT_PUBLIC_API_URL must start with http:// or https://');
  console.error('Current value:', apiUrl);
  process.exit(1);
}

console.log('✅ Environment variables validated!\n');
