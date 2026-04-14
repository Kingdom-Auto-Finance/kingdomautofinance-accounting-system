'use client';

import { useEffect, useState } from 'react';
import { Download, FileText } from 'lucide-react';
import { metro2API, type Metro2FileRow } from '@/lib/api';

export default function FileHistoryPage() {
  const [files, setFiles] = useState<Metro2FileRow[]>([]);
  useEffect(() => {
    metro2API.listFiles(200).then(r => setFiles(r.data));
  }, []);

  return (
    <div className="border rounded bg-white overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-left">
          <tr>
            <th className="px-3 py-2">Filename</th>
            <th className="px-3 py-2">As-of</th>
            <th className="px-3 py-2 text-right">Records</th>
            <th className="px-3 py-2 text-right">Balance</th>
            <th className="px-3 py-2 text-right">Size</th>
            <th className="px-3 py-2">SHA-256</th>
            <th className="px-3 py-2">Generated</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {files.map(f => (
            <tr key={f.id} className="border-t">
              <td className="px-3 py-2 font-mono text-xs">
                <FileText className="w-3 h-3 inline mr-1" />
                {f.filename}
              </td>
              <td className="px-3 py-2 text-xs">{f.as_of_date}</td>
              <td className="px-3 py-2 text-right">{f.record_count}</td>
              <td className="px-3 py-2 text-right">
                ${Number(f.total_current_balance).toLocaleString()}
              </td>
              <td className="px-3 py-2 text-right text-xs">{f.size_bytes} B</td>
              <td className="px-3 py-2 text-xs font-mono truncate max-w-[200px]">
                {f.sha256.slice(0, 16)}…
              </td>
              <td className="px-3 py-2 text-xs">
                {new Date(f.generated_at).toLocaleString()}
              </td>
              <td className="px-3 py-2">
                <a
                  href={metro2API.downloadFileUrl(f.id)}
                  className="inline-flex items-center gap-1 text-blue-600 hover:underline text-xs"
                >
                  <Download className="w-3 h-3" /> Download
                </a>
              </td>
            </tr>
          ))}
          {files.length === 0 && (
            <tr>
              <td colSpan={8} className="text-center py-6 text-muted-foreground">
                No files in history.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
