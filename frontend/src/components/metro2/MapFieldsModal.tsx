'use client';

/**
 * Map Fields Modal - Layer 1 of the six-layer guardrail system.
 *
 * Mirrors Switch Labs' Map Fields modal:
 *   - live counter at the top ("43 headers · 26 mapped · 17/19 required")
 *   - required/recommended/optional badges
 *   - hard-stop gate on Process button until every required field is mapped
 *   - per-field format hint, sample value, and description tooltip
 *   - auto-suggestions based on header name similarity
 *   - save / load mapping templates
 */

import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Save,
  X,
  XCircle,
} from 'lucide-react';
import {
  metro2API,
  type MappingCheck,
  type MappingSuggestion,
  type Metro2Field,
  type Metro2Schema,
  type ValidationReportDTO,
} from '@/lib/api';

interface Props {
  batchId: string;
  filename: string;
  headers: string[];
  suggestions: MappingSuggestion[];
  sampleRows: Record<string, string>[];
  onClose: () => void;
  onAccepted: (result: { inserted: number; skipped: number }) => void;
}

const badgeClass = (importance: string | null | undefined) => {
  switch (importance) {
    case 'required':
      return 'bg-red-100 text-red-700 border-red-200';
    case 'recommended':
      return 'bg-amber-100 text-amber-700 border-amber-200';
    case 'optional':
      return 'bg-gray-100 text-gray-600 border-gray-200';
    default:
      return 'bg-gray-50 text-gray-500 border-gray-200';
  }
};

export default function MapFieldsModal({
  batchId,
  filename,
  headers,
  suggestions,
  sampleRows,
  onClose,
  onAccepted,
}: Props) {
  const [schema, setSchema] = useState<Metro2Schema | null>(null);
  const [templates, setTemplates] = useState<any[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [mappingCheck, setMappingCheck] = useState<MappingCheck | null>(null);
  const [validation, setValidation] = useState<ValidationReportDTO | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saveName, setSaveName] = useState('');

  useEffect(() => {
    metro2API.getSchema().then(setSchema).catch(e => setErr(String(e)));
    metro2API
      .listMappingTemplates()
      .then(r => setTemplates(r.data))
      .catch(() => {});
  }, []);

  // Seed from suggestions on first render once schema arrives.
  useEffect(() => {
    if (!schema) return;
    const initial: Record<string, string> = {};
    suggestions.forEach(s => {
      if (s.suggested_field && s.confidence >= 0.8) {
        initial[s.source_column] = s.suggested_field;
      }
    });
    setMapping(initial);
  }, [schema, suggestions]);

  const fieldsByName = useMemo(() => {
    const map = new Map<string, Metro2Field>();
    (schema?.fields || []).forEach(f => map.set(f.name, f));
    return map;
  }, [schema]);

  const runValidation = async () => {
    if (!batchId) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await metro2API.validateMapping(batchId, mapping);
      setMappingCheck(res.mapping);
      setValidation(res.validation);
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const process = async (force: boolean) => {
    setBusy(true);
    setErr(null);
    try {
      const res = await metro2API.acceptUpload(batchId, mapping, force);
      onAccepted({ inserted: res.inserted, skipped: res.skipped });
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const loadTemplate = (tpl: any) => {
    if (!tpl?.mapping) return;
    setMapping({ ...tpl.mapping });
  };

  const saveTemplate = async () => {
    if (!saveName.trim()) return;
    try {
      await metro2API.saveMappingTemplate({
        name: saveName.trim(),
        mapping,
      });
      const r = await metro2API.listMappingTemplates();
      setTemplates(r.data);
      setSaveName('');
    } catch (e: any) {
      setErr(String(e.message || e));
    }
  };

  const setHeaderTarget = (header: string, target: string) => {
    setMapping(prev => {
      const next = { ...prev };
      if (!target) delete next[header];
      else next[header] = target;
      return next;
    });
  };

  const usedFields = useMemo(() => new Set(Object.values(mapping)), [mapping]);

  const counts = useMemo(() => {
    const mapped = Object.keys(mapping).length;
    const requiredTotal = schema?.counts.required ?? 0;
    const mappedRequired = Array.from(usedFields).filter(
      f => fieldsByName.get(f)?.importance === 'required',
    ).length;
    return { mapped, requiredTotal, mappedRequired };
  }, [mapping, usedFields, schema, fieldsByName]);

  const canProcess = mappingCheck?.is_valid === true;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-6xl max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Map Fields</h2>
            <div className="text-xs text-muted-foreground">{filename}</div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-900"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Live counter */}
        <div className="px-6 py-3 bg-gray-50 border-b flex flex-wrap items-center gap-4 text-sm">
          <span className="font-medium">
            {headers.length} headers detected
          </span>
          <span className="text-muted-foreground">·</span>
          <span>
            <span className="font-medium">{counts.mapped}</span> mapped
          </span>
          <span className="text-muted-foreground">·</span>
          <span
            className={
              counts.mappedRequired < counts.requiredTotal
                ? 'text-red-600 font-medium'
                : 'text-green-700 font-medium'
            }
          >
            {counts.mappedRequired}/{counts.requiredTotal} required
          </span>
          {mappingCheck && !mappingCheck.is_valid && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-100 text-red-700 text-xs">
              <AlertTriangle className="w-3 h-3" />
              {mappingCheck.missing_required.length} required field(s) need
              attention
            </span>
          )}
          {validation && (
            <span className="ml-auto inline-flex items-center gap-3">
              {validation.fatal_count > 0 && (
                <span className="inline-flex items-center gap-1 text-red-700">
                  <XCircle className="w-4 h-4" />
                  {validation.fatal_count} fatal
                </span>
              )}
              {validation.warning_count > 0 && (
                <span className="inline-flex items-center gap-1 text-amber-700">
                  <AlertTriangle className="w-4 h-4" />
                  {validation.warning_count} warning
                </span>
              )}
              {validation.fatal_count === 0 && validation.warning_count === 0 && (
                <span className="inline-flex items-center gap-1 text-green-700">
                  <CheckCircle2 className="w-4 h-4" /> Clean
                </span>
              )}
            </span>
          )}
        </div>

        {/* Templates row */}
        <div className="px-6 py-2 border-b bg-white flex flex-wrap gap-2 items-center text-sm">
          <span className="text-muted-foreground">Templates:</span>
          {templates.length === 0 && (
            <span className="text-xs text-muted-foreground">(none saved)</span>
          )}
          {templates.map(t => (
            <button
              key={t.id}
              className="px-2 py-1 text-xs border rounded hover:bg-gray-100"
              onClick={() => loadTemplate(t)}
            >
              {t.name}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <input
              type="text"
              placeholder="Template name"
              value={saveName}
              onChange={e => setSaveName(e.target.value)}
              className="px-2 py-1 text-xs border rounded"
            />
            <button
              onClick={saveTemplate}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs border rounded bg-white hover:bg-gray-100"
            >
              <Save className="w-3 h-3" /> Save
            </button>
          </div>
        </div>

        {/* Mapping table */}
        <div className="flex-1 overflow-auto px-6 py-4">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0">
              <tr className="text-left">
                <th className="py-2 pr-4 w-1/4">CSV Header</th>
                <th className="py-2 pr-4 w-1/4">Sample Value</th>
                <th className="py-2 pr-4 w-1/3">Map to Metro 2 Field</th>
                <th className="py-2">Field Info</th>
              </tr>
            </thead>
            <tbody>
              {headers.map(header => {
                const suggestion = suggestions.find(
                  s => s.source_column === header,
                );
                const mapped = mapping[header];
                const fld = mapped ? fieldsByName.get(mapped) : undefined;
                const sample =
                  suggestion?.sample_values?.[0] ||
                  sampleRows[0]?.[header] ||
                  '';

                return (
                  <tr key={header} className="border-b last:border-b-0">
                    <td className="py-2 pr-4 font-mono text-xs">{header}</td>
                    <td className="py-2 pr-4 text-muted-foreground truncate">
                      {sample}
                    </td>
                    <td className="py-2 pr-4">
                      <select
                        value={mapped || ''}
                        onChange={e => setHeaderTarget(header, e.target.value)}
                        className="w-full px-2 py-1 border rounded text-sm"
                      >
                        <option value="">— skip —</option>
                        {(schema?.fields || []).map(f => (
                          <option
                            key={f.name}
                            value={f.name}
                            disabled={
                              usedFields.has(f.name) &&
                              mapping[header] !== f.name
                            }
                          >
                            {f.label}{' '}
                            {f.importance === 'required'
                              ? '★'
                              : f.importance === 'recommended'
                                ? '◆'
                                : ''}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2 align-top">
                      {fld ? (
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-1">
                            <span
                              className={
                                'inline-block text-xs border rounded px-1.5 py-0.5 ' +
                                badgeClass(fld.importance)
                              }
                            >
                              {fld.importance}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {fld.format}
                            </span>
                          </div>
                          <div
                            className="text-xs text-gray-600 flex items-start gap-1"
                            title={fld.description}
                          >
                            <Info className="w-3 h-3 mt-0.5 shrink-0" />
                            <span className="line-clamp-2">
                              {fld.description}
                            </span>
                          </div>
                        </div>
                      ) : suggestion?.suggested_field ? (
                        <div className="text-xs text-muted-foreground">
                          Suggested:{' '}
                          <button
                            className="underline"
                            onClick={() =>
                              setHeaderTarget(
                                header,
                                suggestion.suggested_field!,
                              )
                            }
                          >
                            {fieldsByName.get(suggestion.suggested_field)
                              ?.label || suggestion.suggested_field}
                          </button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {mappingCheck && mappingCheck.missing_required.length > 0 && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-sm">
              <div className="font-medium text-red-800 mb-1 flex items-center gap-1">
                <AlertTriangle className="w-4 h-4" />
                {mappingCheck.missing_required.length} required fields
                unmapped
              </div>
              <div className="text-xs text-red-700">
                {mappingCheck.missing_required.join(', ')}
              </div>
            </div>
          )}

          {validation && validation.findings.length > 0 && (
            <div className="mt-4 border rounded">
              <div className="px-3 py-2 bg-gray-50 border-b text-xs font-medium">
                Row-level validation ({validation.findings.length} finding(s))
              </div>
              <div className="max-h-48 overflow-auto text-xs">
                {validation.findings.slice(0, 100).map((f, i) => (
                  <div
                    key={i}
                    className={
                      'px-3 py-1.5 border-b last:border-b-0 flex gap-3 ' +
                      (f.severity === 'FATAL' ? 'bg-red-50' : 'bg-amber-50')
                    }
                  >
                    <span className="font-mono shrink-0">
                      {f.severity === 'FATAL' ? '✕' : '!'}
                    </span>
                    <span className="font-mono text-muted-foreground shrink-0">
                      {f.row_index != null ? `#${f.row_index + 1}` : ''}
                    </span>
                    <span className="font-mono shrink-0">{f.code}</span>
                    <span>{f.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer / actions */}
        <div className="px-6 py-3 border-t bg-gray-50 flex items-center justify-between">
          <div className="text-xs text-red-600">{err}</div>
          <div className="flex gap-2">
            <button
              onClick={runValidation}
              disabled={busy}
              className="px-3 py-1.5 text-sm border rounded bg-white hover:bg-gray-100"
            >
              {busy ? 'Validating…' : 'Run Validation'}
            </button>
            <button
              onClick={() => process(false)}
              disabled={busy || !canProcess}
              className={
                'px-4 py-1.5 text-sm rounded text-white ' +
                (canProcess
                  ? 'bg-blue-600 hover:bg-blue-700'
                  : 'bg-gray-300 cursor-not-allowed')
              }
            >
              Process
            </button>
            {validation && validation.fatal_count > 0 && canProcess && (
              <button
                onClick={() => process(true)}
                disabled={busy}
                className="px-3 py-1.5 text-sm rounded border border-red-300 text-red-700 hover:bg-red-50"
              >
                Force Process ({validation.fatal_count} fatal)
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
