'use client';

import { useEffect, useState } from 'react';
import { Download, FileText, ShieldCheck, AlertTriangle, XCircle, CheckCircle2 } from 'lucide-react';
import { metro2API, type Metro2FileRow } from '@/lib/api';

export default function FilesPage() {
  const [asOf, setAsOf] = useState<string>('');
  const [files, setFiles] = useState<Metro2FileRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);
  const [enforceMin, setEnforceMin] = useState(true);
  const [lastResult, setLastResult] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    const r = await metro2API.listFiles();
    setFiles(r.data);
  };

  useEffect(() => {
    load();
  }, []);

  const generate = async () => {
    setBusy(true);
    setErr(null);
    setLastResult(null);
    try {
      const r = await metro2API.generateFile({
        as_of_date: asOf || undefined,
        force,
        enforce_minimum: enforceMin,
      });
      setLastResult(r);
      await load();
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="border rounded bg-white p-4">
        <div className="font-medium mb-3 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4" /> Generate Metro 2 File
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <label className="text-sm">
            <div className="text-xs text-muted-foreground mb-0.5">
              As-of date (YYYYMMDD)
            </div>
            <input
              type="text"
              placeholder="auto"
              value={asOf}
              onChange={e => setAsOf(e.target.value)}
              className="px-2 py-1 border rounded w-40 font-mono"
            />
          </label>
          <label className="inline-flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={enforceMin}
              onChange={e => setEnforceMin(e.target.checked)}
            />
            Enforce Experian 100-account minimum
          </label>
          <label className="inline-flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={force}
              onChange={e => setForce(e.target.checked)}
            />
            Force (override fatal findings)
          </label>
          <button
            onClick={generate}
            disabled={busy}
            className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:bg-gray-300"
          >
            {busy ? 'Generating…' : 'Generate File'}
          </button>
        </div>
        {err && (
          <div className="mt-3 text-sm text-red-700 flex items-start gap-1">
            <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
            {err}
          </div>
        )}
        {lastResult && (
          <div className="mt-3 p-3 border rounded bg-green-50 text-sm">
            <div className="flex items-center gap-2 font-medium text-green-800">
              <CheckCircle2 className="w-4 h-4" />
              {lastResult.filename} generated ({lastResult.record_count} records,{' '}
              ${Number(lastResult.total_current_balance).toLocaleString()} balance)
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              SHA-256: <span className="font-mono">{lastResult.sha256}</span>
            </div>
            {lastResult.validation.warning_count > 0 && (
              <div className="text-xs text-amber-700 mt-1 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                {lastResult.validation.warning_count} warning(s) - review
                before uploading to Experian.
              </div>
            )}
          </div>
        )}
      </section>

      <section>
        <div className="font-medium mb-2">Recent Files</div>
        <div className="border rounded bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left">
              <tr>
                <th className="px-3 py-2">Filename</th>
                <th className="px-3 py-2">As-of</th>
                <th className="px-3 py-2 text-right">Records</th>
                <th className="px-3 py-2 text-right">Balance</th>
                <th className="px-3 py-2 text-right">Past Due</th>
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
                  <td className="px-3 py-2 text-right">
                    ${Number(f.total_past_due).toLocaleString()}
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
                  <td colSpan={7} className="text-center py-6 text-muted-foreground">
                    No files yet. Generate one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
