'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function Metro2Index() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/credit-reports/metro2/records');
  }, [router]);
  return null;
}
