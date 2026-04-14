'use client';

import { useEffect, useState } from 'react';
import { metro2API, type Metro2FileRow } from '@/lib/api';

export default function TransmissionsPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [files, setFiles] = useState<Metro2FileRow[]>([]);
  const [form, setForm] = useState({
    file_id: '',
    transmitted_at: new Date().toISOString(),
    confirmation_ref: '',
    notes: '',
  });

  const load = () => metro2API.listTransmissions().then(r => setRows(r.data));
  useEffect(() => {
    load();
    metro2API.listFiles().then(r => setFiles(r.data));
  }, []);

  const submit = async () => {
    if (!form.file_id) return;
    await metro2API.logTransmission(form);
    setForm({
      file_id: '',
      transmitted_at: new Date().toISOString(),
      confirmation_ref: '',
      notes: '',
    });
    load();
  };

  return (
    <div className="space-y-4">
      <div className="border rounded bg-card p-3 text-sm">
        <div className="font-medium mb-2">Log a transmission</div>
        <p className="text-xs text-muted-foreground mb-2">
          After uploading the .txt to data-eft.experian.com, record the
          transmission here so the response file can be linked back.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <select
            className="px-2 py-1 border rounded text-sm"
            value={form.file_id}
            onChange={e => setForm({ ...form, file_id: e.target.value })}
          >
            <option value="">— pick file —</option>
            {files.map(f => (
              <option key={f.id} value={f.id}>
                {f.filename} ({f.record_count})
              </option>
            ))}
          </select>
          <input
            placeholder="transmitted_at ISO"
            className="px-2 py-1 border rounded text-xs font-mono"
            value={form.transmitted_at}
            onChange={e => setForm({ ...form, transmitted_at: e.target.value })}
          />
          <input
            placeholder="confirmation ref"
            className="px-2 py-1 border rounded"
            value={form.confirmation_ref}
            onChange={e => setForm({ ...form, confirmation_ref: e.target.value })}
          />
          <input
            placeholder="notes"
            className="px-2 py-1 border rounded"
            value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })}
          />
        </div>
        <button
          onClick={submit}
          className="mt-2 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Log
        </button>
      </div>

      <div className="border rounded bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left">
            <tr>
              <th className="px-3 py-2">When</th>
              <th className="px-3 py-2">File</th>
              <th className="px-3 py-2">Confirmation</th>
              <th className="px-3 py-2">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} className="border-t">
                <td className="px-3 py-2 text-xs">
                  {new Date(r.transmitted_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {r.metro2_files?.filename || r.file_id}
                </td>
                <td className="px-3 py-2 text-xs">{r.confirmation_ref}</td>
                <td className="px-3 py-2 text-xs">{r.notes}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="text-center py-6 text-muted-foreground">
                  No transmissions logged yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
