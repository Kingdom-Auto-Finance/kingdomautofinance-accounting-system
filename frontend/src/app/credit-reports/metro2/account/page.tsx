'use client';

import { useEffect, useState } from 'react';
import { metro2API } from '@/lib/api';

export default function AccountPage() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  useEffect(() => {
    metro2API.getAccount().then(setData).catch(() => {});
  }, []);

  if (!data) return <div className="text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="border rounded bg-white p-6 max-w-xl">
      <div className="font-medium mb-3">Subscriber settings</div>
      <p className="text-xs text-muted-foreground mb-4">
        Read-only in v1. Edit{' '}
        <span className="font-mono">
          backend/app/services/metro2_schema.py
        </span>{' '}
        to change.
      </p>
      <dl className="grid grid-cols-1 gap-3 text-sm">
        {Object.entries(data)
          .filter(([k]) => k !== 'read_only')
          .map(([k, v]) => (
            <div key={k} className="border-b pb-2">
              <dt className="text-xs text-muted-foreground">{k}</dt>
              <dd className="font-mono text-sm">{String(v)}</dd>
            </div>
          ))}
      </dl>
    </div>
  );
}
