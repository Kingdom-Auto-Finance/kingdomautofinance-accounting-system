'use client';

import { useEffect, useState } from 'react';
import { metro2API } from '@/lib/api';

export default function DisputesPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [status, setStatus] = useState('');
  const [form, setForm] = useState({
    record_id: '',
    dispute_code: '',
    received_at: new Date().toISOString(),
    notes: '',
  });

  const load = () => metro2API.listDisputes(status || undefined).then(r => setRows(r.data));
  useEffect(() => {
    load();
  }, [status]);

  const create = async () => {
    await metro2API.createDispute(form);
    setForm({ record_id: '', dispute_code: '', received_at: new Date().toISOString(), notes: '' });
    load();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <select
          className="py-2 px-2 border rounded text-sm"
          value={status}
          onChange={e => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="investigating">Investigating</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      <div className="border rounded bg-card p-3 text-sm">
        <div className="font-medium mb-2">Log new dispute</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <input
            placeholder="record_id (optional)"
            className="px-2 py-1 border rounded text-xs font-mono"
            value={form.record_id}
            onChange={e => setForm({ ...form, record_id: e.target.value })}
          />
          <input
            placeholder="dispute code"
            className="px-2 py-1 border rounded"
            value={form.dispute_code}
            onChange={e => setForm({ ...form, dispute_code: e.target.value })}
          />
          <input
            placeholder="received_at ISO"
            className="px-2 py-1 border rounded text-xs font-mono"
            value={form.received_at}
            onChange={e => setForm({ ...form, received_at: e.target.value })}
          />
          <input
            placeholder="notes"
            className="px-2 py-1 border rounded"
            value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })}
          />
        </div>
        <button
          onClick={create}
          className="mt-2 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Create
        </button>
      </div>

      <div className="border rounded bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left">
            <tr>
              <th className="px-3 py-2">Received</th>
              <th className="px-3 py-2">Code</th>
              <th className="px-3 py-2">Record</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} className="border-t">
                <td className="px-3 py-2 text-xs">
                  {new Date(r.received_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{r.dispute_code || '—'}</td>
                <td className="px-3 py-2 font-mono text-xs">{r.record_id || '—'}</td>
                <td className="px-3 py-2">{r.resolution_status}</td>
                <td className="px-3 py-2 text-xs">{r.notes}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-6 text-muted-foreground">
                  No disputes logged.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
