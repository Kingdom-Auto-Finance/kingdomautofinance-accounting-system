'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Edit2,
  Eye,
  EyeOff,
  Search,
  XCircle,
} from 'lucide-react';
import { metro2API, type Metro2Record } from '@/lib/api';

const validationBadge = (s: string | undefined) => {
  if (s === 'clean')
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded bg-green-100 text-green-700">
        <CheckCircle2 className="w-3 h-3" /> clean
      </span>
    );
  if (s === 'warning')
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded bg-amber-100 text-amber-700">
        <AlertTriangle className="w-3 h-3" /> warning
      </span>
    );
  if (s === 'fatal')
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded bg-red-100 text-red-700">
        <XCircle className="w-3 h-3" /> fatal
      </span>
    );
  return <span className="text-xs text-muted-foreground">—</span>;
};

export default function RecordsPage() {
  const [data, setData] = useState<Metro2Record[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [q, setQ] = useState('');
  const [filterOrigin, setFilterOrigin] = useState('');
  const [filterValidation, setFilterValidation] = useState('');
  const [onlyActive, setOnlyActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Metro2Record | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const r = await metro2API.listRecords({
        q: q || undefined,
        origin: filterOrigin || undefined,
        validation_status: filterValidation || undefined,
        only_active: onlyActive,
        page,
        page_size: pageSize,
      });
      setData(r.data);
      setTotal(r.total);
    } finally {
      setBusy(false);
    }
  }, [q, filterOrigin, filterValidation, onlyActive, page, pageSize]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-2 top-2.5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search account # or name"
            value={q}
            onChange={e => setQ(e.target.value)}
            className="pl-8 pr-3 py-2 border rounded text-sm w-64"
          />
        </div>
        <select
          className="py-2 px-2 border rounded text-sm"
          value={filterOrigin}
          onChange={e => setFilterOrigin(e.target.value)}
        >
          <option value="">All origins</option>
          <option value="cycle">Cycle</option>
          <option value="manual">Manual</option>
        </select>
        <select
          className="py-2 px-2 border rounded text-sm"
          value={filterValidation}
          onChange={e => setFilterValidation(e.target.value)}
        >
          <option value="">Any validation</option>
          <option value="clean">Clean</option>
          <option value="warning">Warning</option>
          <option value="fatal">Fatal</option>
        </select>
        <label className="inline-flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={onlyActive}
            onChange={e => setOnlyActive(e.target.checked)}
          />
          Only active
        </label>
        <button
          onClick={() => {
            setPage(1);
            load();
          }}
          className="px-3 py-1.5 text-sm border rounded hover:bg-gray-100"
        >
          Apply
        </button>
        <div className="ml-auto text-sm text-muted-foreground">
          {busy ? 'Loading…' : `${total.toLocaleString()} record${total === 1 ? '' : 's'}`}
        </div>
      </div>

      <div className="border rounded bg-white overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left">
            <tr>
              <th className="px-3 py-2">Account #</th>
              <th className="px-3 py-2">Consumer</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2 text-right">Balance</th>
              <th className="px-3 py-2 text-right">Past Due</th>
              <th className="px-3 py-2">Origin</th>
              <th className="px-3 py-2">Validation</th>
              <th className="px-3 py-2">Active</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {data.map(r => (
              <tr key={r.id} className="border-t hover:bg-gray-50">
                <td className="px-3 py-2 font-mono text-xs">
                  {r.consumer_account_number}
                </td>
                <td className="px-3 py-2">
                  {(r.surname || '').toUpperCase()}, {(r.first_name || '')}
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {r.account_status}
                </td>
                <td className="px-3 py-2 text-right">
                  ${Number(r.current_balance || 0).toLocaleString()}
                </td>
                <td className="px-3 py-2 text-right">
                  ${Number(r.amount_past_due || 0).toLocaleString()}
                </td>
                <td className="px-3 py-2 text-xs">
                  <span
                    className={
                      'px-1.5 py-0.5 rounded ' +
                      (r.origin === 'cycle'
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-purple-100 text-purple-700')
                    }
                  >
                    {r.origin}
                  </span>
                </td>
                <td className="px-3 py-2">
                  {validationBadge(r.last_validated_status)}
                </td>
                <td className="px-3 py-2 text-xs">
                  {r.is_active ? (
                    <Eye className="w-4 h-4 text-green-600" />
                  ) : (
                    <EyeOff className="w-4 h-4 text-gray-400" />
                  )}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => setSelected(r)}
                    className="text-blue-600 hover:underline inline-flex items-center gap-1 text-xs"
                  >
                    <Edit2 className="w-3 h-3" /> View
                  </button>
                </td>
              </tr>
            ))}
            {data.length === 0 && !busy && (
              <tr>
                <td colSpan={9} className="text-center py-8 text-muted-foreground">
                  No records yet. Upload a CSV in the File Upload tab.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {total > pageSize && (
        <div className="flex items-center gap-2 justify-end text-sm">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-2 py-1 border rounded disabled:opacity-40"
          >
            Prev
          </button>
          <span>
            Page {page} of {Math.ceil(total / pageSize)}
          </span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={page * pageSize >= total}
            className="px-2 py-1 border rounded disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}

      {selected && (
        <RecordDrawer
          record={selected}
          onClose={() => setSelected(null)}
          onChanged={() => {
            setSelected(null);
            load();
          }}
        />
      )}
    </div>
  );
}

// Inline drawer component — kept here to avoid yet another file.
function RecordDrawer({
  record,
  onClose,
  onChanged,
}: {
  record: Metro2Record;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    metro2API
      .getRecordHistory(record.id)
      .then(r => setHistory(r.data))
      .catch(() => {});
  }, [record.id]);

  const run = async (fn: () => Promise<any>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      onChanged();
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-end z-40">
      <div className="bg-white w-full sm:max-w-2xl h-full sm:h-auto sm:max-h-[92vh] overflow-auto shadow-xl">
        <div className="p-4 border-b flex items-center justify-between">
          <div>
            <div className="text-xs text-muted-foreground">Account</div>
            <div className="font-semibold font-mono">
              {record.consumer_account_number}
            </div>
          </div>
          <button onClick={onClose} className="text-gray-500">
            Close
          </button>
        </div>
        <div className="p-4 grid grid-cols-2 gap-3 text-sm">
          {Object.entries(record)
            .filter(([k]) => !k.startsWith('last_validation_issues'))
            .map(([k, v]) => (
              <div key={k} className="border-b pb-1">
                <div className="text-xs text-muted-foreground">{k}</div>
                <div className="font-mono text-xs break-all">
                  {v === null || v === undefined ? '—' : String(v)}
                </div>
              </div>
            ))}
        </div>
        {record.last_validation_issues && record.last_validation_issues.length > 0 && (
          <div className="p-4 border-t">
            <div className="font-medium text-sm mb-2">Validation findings</div>
            <div className="space-y-1 text-xs">
              {record.last_validation_issues.map((f: any, i: number) => (
                <div key={i}>
                  <span
                    className={
                      f.severity === 'FATAL' ? 'text-red-700' : 'text-amber-700'
                    }
                  >
                    {f.severity}
                  </span>{' '}
                  <span className="font-mono">{f.code}</span> — {f.message}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="p-4 border-t flex gap-2">
          <button
            disabled={busy}
            className="px-3 py-1.5 text-sm border rounded hover:bg-gray-100"
            onClick={() => run(() => metro2API.revalidateRecord(record.id))}
          >
            Re-validate
          </button>
          {record.is_active ? (
            <button
              disabled={busy}
              className="px-3 py-1.5 text-sm border rounded text-red-600 hover:bg-red-50"
              onClick={() => run(() => metro2API.deactivateRecord(record.id))}
            >
              Deactivate
            </button>
          ) : (
            <button
              disabled={busy}
              className="px-3 py-1.5 text-sm border rounded text-green-700 hover:bg-green-50"
              onClick={() => run(() => metro2API.reactivateRecord(record.id))}
            >
              Reactivate
            </button>
          )}
          {err && <span className="text-xs text-red-600 self-center">{err}</span>}
        </div>
        {history.length > 0 && (
          <div className="p-4 border-t">
            <div className="font-medium text-sm mb-2">History</div>
            <div className="space-y-1 text-xs">
              {history.map(h => (
                <div key={h.id} className="flex gap-2">
                  <span className="text-muted-foreground">
                    {new Date(h.changed_at).toLocaleString()}
                  </span>
                  <span className="font-mono">{h.change_type}</span>
                  {h.field_name && <span>{h.field_name}</span>}
                  {h.note && <span className="italic">{h.note}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
