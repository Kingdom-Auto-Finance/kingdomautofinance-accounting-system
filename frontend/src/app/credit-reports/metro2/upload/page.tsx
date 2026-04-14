'use client';

import { useRef, useState } from 'react';
import { Upload, FileText, AlertCircle, CheckCircle2 } from 'lucide-react';
import { metro2API, type MappingSuggestion } from '@/lib/api';
import MapFieldsModal from '@/components/metro2/MapFieldsModal';

type ParseResult = Awaited<ReturnType<typeof metro2API.uploadFile>>;

export default function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<ParseResult | null>(null);
  const [lastAccept, setLastAccept] = useState<{
    inserted: number;
    skipped: number;
    skip_reasons?: { row_index: number; account_number?: string; error: string }[];
  } | null>(null);

  const handleFile = async (file: File) => {
    setBusy(true);
    setErr(null);
    setLastAccept(null);
    try {
      const r = await metro2API.uploadFile(file);
      setResult(r);
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="border-2 border-dashed rounded-lg p-10 text-center bg-card">
        <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
        <p className="text-sm mb-3">
          Upload a CSV or XLSX file. We’ll parse the headers and open the
          Map Fields modal.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={e => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />
        <button
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:bg-muted"
        >
          {busy ? 'Parsing…' : 'Choose File'}
        </button>
        {err && (
          <div className="mt-3 inline-flex items-center gap-1 text-sm text-red-600 dark:text-red-400">
            <AlertCircle className="w-4 h-4" />
            {err}
          </div>
        )}
      </section>

      {lastAccept && (
        <div className="space-y-2">
          <div
            className={
              'p-3 rounded border text-sm flex items-center gap-2 ' +
              (lastAccept.inserted > 0
                ? 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-900 text-green-800 dark:text-green-200'
                : 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-200')
            }
          >
            <CheckCircle2 className="w-4 h-4" />
            Accepted {lastAccept.inserted} record(s) into the ledger
            {lastAccept.skipped > 0 && ` · skipped ${lastAccept.skipped}`}.
          </div>
          {lastAccept.skip_reasons && lastAccept.skip_reasons.length > 0 && (
            <details className="border border-border rounded text-xs bg-card">
              <summary className="px-3 py-2 cursor-pointer font-medium hover:bg-muted/40">
                Why were rows skipped? ({lastAccept.skip_reasons.length} shown)
              </summary>
              <div className="px-3 py-2 max-h-64 overflow-auto space-y-1">
                {lastAccept.skip_reasons.map((r, i) => (
                  <div key={i} className="flex gap-3 text-muted-foreground">
                    <span className="font-mono w-12">#{r.row_index + 1}</span>
                    <span className="font-mono w-32 truncate text-foreground">
                      {r.account_number || '—'}
                    </span>
                    <span className="flex-1 text-red-600 dark:text-red-400">
                      {r.error}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {result && (
        <section className="border rounded bg-card p-4 text-sm">
          <div className="flex items-center gap-2 mb-2 font-medium">
            <FileText className="w-4 h-4" /> {result.filename}
          </div>
          <div className="text-muted-foreground mb-3">
            {result.row_count} rows · {result.headers.length} columns
          </div>
          <MapFieldsModal
            batchId={result.batch_id}
            filename={result.filename}
            headers={result.headers}
            suggestions={result.suggestions as MappingSuggestion[]}
            sampleRows={result.sample_rows}
            onClose={() => setResult(null)}
            onAccepted={({ inserted, skipped, skip_reasons }) => {
              setLastAccept({ inserted, skipped, skip_reasons });
              setResult(null);
            }}
          />
        </section>
      )}
    </div>
  );
}
