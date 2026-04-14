'use client';

import { useEffect, useState } from 'react';
import { metro2API } from '@/lib/api';

export default function AnalyticsPage() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    metro2API.getAnalytics().then(setData).catch(() => {});
  }, []);

  if (!data) return <div className="text-sm text-muted-foreground">Loading…</div>;

  const Card = ({ label, value }: { label: string; value: any }) => (
    <div className="border rounded p-4 bg-card">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );

  const Dist = ({ title, rows }: { title: string; rows: Record<string, number> }) => {
    const total = Object.values(rows).reduce((a, b) => a + b, 0) || 1;
    return (
      <div className="border rounded p-4 bg-card">
        <div className="font-medium mb-2">{title}</div>
        <div className="space-y-1 text-sm">
          {Object.entries(rows).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2">
              <div className="w-24 text-xs font-mono">{k}</div>
              <div className="flex-1 bg-muted rounded h-2">
                <div
                  className="bg-blue-500 h-2 rounded"
                  style={{ width: `${(v / total) * 100}%` }}
                />
              </div>
              <div className="w-12 text-right text-xs">{v}</div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Card label="Total active records" value={data.total_records} />
        <Card
          label="Total current balance"
          value={`$${Number(data.total_balance).toLocaleString()}`}
        />
        <Card
          label="Total past due"
          value={`$${Number(data.total_past_due).toLocaleString()}`}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Dist title="Account Status" rows={data.status_distribution} />
        <Dist title="Origin" rows={data.origin_distribution} />
        <Dist title="Validation" rows={data.validation_distribution} />
      </div>

      {data.recent_files?.length > 0 && (
        <div className="border rounded p-4 bg-card">
          <div className="font-medium mb-2">Recent files</div>
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="text-left pb-1">File</th>
                <th className="text-right pb-1">Records</th>
                <th className="text-right pb-1">Generated</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_files.map((f: any) => (
                <tr key={f.filename} className="border-t">
                  <td className="py-1 font-mono text-xs">{f.filename}</td>
                  <td className="py-1 text-right">{f.record_count}</td>
                  <td className="py-1 text-right text-xs">
                    {new Date(f.generated_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
