'use client';

import { useEffect, useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import { metro2API } from '@/lib/api';

export default function ResponsesPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [transmissionId, setTransmissionId] = useState<string>('');
  const [transmissions, setTransmissions] = useState<any[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = () => metro2API.listResponses().then(r => setRows(r.data));
  useEffect(() => {
    load();
    metro2API.listTransmissions().then(r => setTransmissions(r.data));
  }, []);

  const handleFile = async (f: File) => {
    await metro2API.uploadResponse(f, transmissionId || undefined);
    load();
  };

  return (
    <div className="space-y-4">
      <div className="border rounded bg-white p-3 text-sm">
        <div className="font-medium mb-2">Upload Experian response file</div>
        <div className="flex gap-2 items-center">
          <select
            className="py-2 px-2 border rounded text-sm"
            value={transmissionId}
            onChange={e => setTransmissionId(e.target.value)}
          >
            <option value="">— optional: link to transmission —</option>
            {transmissions.map(t => (
              <option key={t.id} value={t.id}>
                {t.metro2_files?.filename} ({new Date(t.transmitted_at).toLocaleDateString()})
              </option>
            ))}
          </select>
          <input
            ref={inputRef}
            type="file"
            accept=".txt"
            className="hidden"
            onChange={e => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
          <button
            onClick={() => inputRef.current?.click()}
            className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
          >
            <Upload className="w-4 h-4" /> Upload Response
          </button>
        </div>
      </div>

      <div className="border rounded bg-white overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left">
            <tr>
              <th className="px-3 py-2">Received</th>
              <th className="px-3 py-2">File</th>
              <th className="px-3 py-2">Accepted</th>
              <th className="px-3 py-2">Rejected</th>
              <th className="px-3 py-2">Warnings</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} className="border-t">
                <td className="px-3 py-2 text-xs">
                  {new Date(r.received_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{r.response_filename}</td>
                <td className="px-3 py-2 text-green-700 text-xs">
                  {r.parsed_summary?.accepted ?? '—'}
                </td>
                <td className="px-3 py-2 text-red-700 text-xs">
                  {r.parsed_summary?.rejected ?? '—'}
                </td>
                <td className="px-3 py-2 text-amber-700 text-xs">
                  {r.parsed_summary?.warnings ?? '—'}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-6 text-muted-foreground">
                  No responses uploaded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
