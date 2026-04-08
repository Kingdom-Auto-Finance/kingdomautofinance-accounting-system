'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Layout from '@/components/Layout';
import {
  creditReportAPI,
  type RunSummary,
  type RunDetail,
  type RunItem,
  type Validation,
} from '@/lib/api';
import { downloadCSV, formatDate } from '@/lib/utils';
import {
  ShieldCheck,
  Upload,
  AlertCircle,
  CheckCircle2,
  Info,
  XCircle,
  Download,
  FileText,
  X,
  Building2,
  User,
  Check,
  Ban,
  Clock,
  Lock,
} from 'lucide-react';

type BucketKey = 'ready' | 'review' | 'excluded' | 'carried';

const BUCKET_LABELS: Record<BucketKey, string> = {
  ready: 'Ready',
  review: 'Needs Review',
  excluded: 'Excluded',
  carried: 'Carried over',
};

const BUCKET_COLORS: Record<BucketKey, string> = {
  ready: 'text-green-700 bg-green-100 dark:bg-green-900/30 dark:text-green-300',
  review: 'text-amber-700 bg-amber-100 dark:bg-amber-900/30 dark:text-amber-300',
  excluded: 'text-gray-700 bg-gray-100 dark:bg-gray-800 dark:text-gray-300',
  carried: 'text-blue-700 bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300',
};

export default function CreditReportsPage() {
  // ── Global state ─────────────────────────────────────────────────────
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [currentRun, setCurrentRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Upload form state
  const [dealFile, setDealFile] = useState<File | null>(null);
  const [addressFile, setAddressFile] = useState<File | null>(null);
  const [cycleMonth, setCycleMonth] = useState<string>(defaultCycleMonth());
  const [uploading, setUploading] = useState(false);

  // Preview state
  const [activeBucket, setActiveBucket] = useState<BucketKey>('ready');
  const [bucketItems, setBucketItems] = useState<RunItem[]>([]);
  const [bucketTotal, setBucketTotal] = useState(0);
  const [bucketLoading, setBucketLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showInstructions, setShowInstructions] = useState(false);

  // ── Initial load ─────────────────────────────────────────────────────
  useEffect(() => {
    loadRuns();
  }, []);

  const loadRuns = async () => {
    try {
      const resp = await creditReportAPI.listRuns(12);
      setRuns(resp.data);
      // Auto-select the most recent run if we don't have one selected
      if (resp.data.length && !currentRun) {
        const latest = resp.data[0];
        const detail = await creditReportAPI.getRun(latest.id);
        setCurrentRun(detail);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load runs');
    }
  };

  // ── Reload items whenever active bucket or run changes ──────────────
  useEffect(() => {
    if (currentRun) {
      loadItems(currentRun.run.id, activeBucket, searchQuery);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRun?.run.id, activeBucket]);

  const loadItems = useCallback(
    async (runId: string, bucket: BucketKey, query: string) => {
      setBucketLoading(true);
      try {
        const resp = await creditReportAPI.listItems(runId, {
          bucket,
          q: query || undefined,
          page: 1,
          page_size: 200,
        });
        setBucketItems(resp.data);
        setBucketTotal(resp.total);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load items');
      } finally {
        setBucketLoading(false);
      }
    },
    []
  );

  // ── Upload handler ───────────────────────────────────────────────────
  const handleUpload = async () => {
    if (!dealFile || !addressFile) {
      setError('Please select both a Deal CSV and an Address CSV.');
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const resp = await creditReportAPI.createDraft(dealFile, addressFile, cycleMonth);
      // Reload the runs list and auto-select the new draft
      await loadRuns();
      const detail = await creditReportAPI.getRun(resp.run_id);
      setCurrentRun(detail);
      setActiveBucket('ready');
      // Scroll to preview
      document.getElementById('preview-section')?.scrollIntoView({ behavior: 'smooth' });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  // ── Search debounced reload ──────────────────────────────────────────
  const handleSearchChange = (val: string) => {
    setSearchQuery(val);
    if (currentRun) {
      loadItems(currentRun.run.id, activeBucket, val);
    }
  };

  // ── Decision handlers ────────────────────────────────────────────────
  const refreshAfterMutation = async () => {
    if (!currentRun) return;
    // Reload the run detail (so counts refresh) and the current bucket list.
    const detail = await creditReportAPI.getRun(currentRun.run.id);
    setCurrentRun(detail);
    loadItems(detail.run.id, activeBucket, searchQuery);
  };

  const handleSetBusinessFlag = async (dealId: string, isBusiness: boolean) => {
    if (!currentRun) return;
    try {
      await creditReportAPI.setBusinessFlag(currentRun.run.id, dealId, {
        is_business: isBusiness,
      });
      await refreshAfterMutation();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update flag');
    }
  };

  const handleSetReviewDecision = async (
    dealId: string,
    decision: 'approve' | 'exclude' | 'defer',
    metro2_status_code?: string,
    fcra_dofi?: string,
    note?: string
  ) => {
    if (!currentRun) return;
    try {
      await creditReportAPI.setReviewDecision(currentRun.run.id, dealId, {
        decision,
        metro2_status_code,
        fcra_dofi,
        note,
      });
      await refreshAfterMutation();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save decision');
    }
  };

  // ── Download handlers ────────────────────────────────────────────────
  const handleDownload = async (bucket: BucketKey) => {
    if (!currentRun) return;
    try {
      const csv = await creditReportAPI.downloadCsv(currentRun.run.id, bucket);
      const cycle = currentRun.run.cycle_month.replace(/-/g, '');
      downloadCSV(csv, `metro2_${bucket}_${cycle}.csv`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed');
    }
  };

  const handleFinalize = async (force: boolean, note?: string) => {
    if (!currentRun) return;
    try {
      const detail = await creditReportAPI.finalize(currentRun.run.id, {
        force,
        note,
      });
      setCurrentRun(detail);
      await loadRuns();
      loadItems(detail.run.id, activeBucket, searchQuery);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Finalize failed');
    }
  };

  const handleDownloadReport = async () => {
    if (!currentRun) return;
    try {
      const text = await creditReportAPI.downloadReport(currentRun.run.id);
      const cycle = currentRun.run.cycle_month.replace(/-/g, '');
      const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `metro2_report_${cycle}.txt`;
      link.click();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed');
    }
  };

  // ── Derived ──────────────────────────────────────────────────────────
  const bucketCounts = useMemo<Record<BucketKey, number>>(() => {
    const r = currentRun?.run;
    return {
      ready: r?.ready_count ?? 0,
      review: r?.review_count ?? 0,
      excluded: r?.excluded_count ?? 0,
      carried: r?.carried_over_count ?? 0,
    };
  }, [currentRun]);

  const fatalValidations = (currentRun?.validations ?? []).filter(
    v => v.severity === 'FATAL'
  );

  return (
    <Layout>
      <div className="space-y-6">
        {/* ── Header ───────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground flex items-center gap-3">
              <ShieldCheck className="w-8 h-8 text-blue-600" />
              Credit Reports
            </h1>
            <p className="text-muted-foreground mt-1">
              Monthly Metro 2 / Experian reporting workflow.
            </p>
          </div>
        </div>

        {/* ── Error banner ────────────────────────────────────────── */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1 text-sm text-red-800 dark:text-red-300">{error}</div>
            <button
              onClick={() => setError(null)}
              className="text-red-600 hover:text-red-800"
              aria-label="Dismiss"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* ── Status banner ──────────────────────────────────────── */}
        <StatusBanner runs={runs} currentRun={currentRun} />

        {/* ── Upload card ────────────────────────────────────────── */}
        <div className="bg-card p-6 rounded-lg shadow border border-border">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold text-foreground">1. Upload CSVs</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Export deals + dealaddresses from MongoDB and upload both files here.
              </p>
            </div>
            <button
              onClick={() => setShowInstructions(true)}
              className="text-sm text-blue-600 hover:text-blue-700 underline"
            >
              How do I export from MongoDB?
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <FileDropZone
              label="Deal export (.csv)"
              file={dealFile}
              onFileChange={setDealFile}
              hint="kingdomautofinance_Deal.csv"
            />
            <FileDropZone
              label="Address export (.csv)"
              file={addressFile}
              onFileChange={setAddressFile}
              hint="kingdomautofinance_Address.csv"
            />
          </div>

          <div className="flex items-end gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-foreground mb-1">
                Cycle month (reporting period)
              </label>
              <input
                type="month"
                value={cycleMonth.slice(0, 7)}
                onChange={e => setCycleMonth(e.target.value + '-01')}
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-blue-500 bg-card text-foreground"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Defaults to last calendar month.
              </p>
            </div>
            <button
              onClick={handleUpload}
              disabled={uploading || !dealFile || !addressFile}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <Upload className="w-4 h-4" />
              {uploading ? 'Processing...' : 'Process upload'}
            </button>
          </div>
        </div>

        {/* ── Preview section ────────────────────────────────────── */}
        {currentRun && (
          <div id="preview-section" className="bg-card p-6 rounded-lg shadow border border-border">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xl font-semibold text-foreground">
                  2. Review accounts
                </h2>
                <p className="text-sm text-muted-foreground mt-1">
                  Cycle {currentRun.run.cycle_month} · Status:{' '}
                  <span className="font-medium">{currentRun.run.status}</span>
                </p>
              </div>
              <input
                type="search"
                placeholder="Search deal ID or name..."
                value={searchQuery}
                onChange={e => handleSearchChange(e.target.value)}
                className="px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-blue-500 bg-card text-foreground w-64"
              />
            </div>

            {/* Bucket tabs */}
            <div className="flex flex-wrap gap-2 mb-4 border-b border-border pb-4">
              {(Object.keys(BUCKET_LABELS) as BucketKey[]).map(b => (
                <button
                  key={b}
                  onClick={() => setActiveBucket(b)}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                    activeBucket === b
                      ? BUCKET_COLORS[b] + ' ring-2 ring-offset-2 ring-offset-card'
                      : 'text-muted-foreground hover:bg-muted/50'
                  }`}
                >
                  {BUCKET_LABELS[b]}{' '}
                  <span className="font-semibold">({bucketCounts[b]})</span>
                </button>
              ))}
            </div>

            {/* Items table */}
            <BucketTable
              bucket={activeBucket}
              items={bucketItems}
              total={bucketTotal}
              loading={bucketLoading}
              isDraft={currentRun.run.status === 'draft'}
              onSetBusinessFlag={handleSetBusinessFlag}
              onSetReviewDecision={handleSetReviewDecision}
            />
          </div>
        )}

        {/* ── Validation panel ───────────────────────────────────── */}
        {currentRun && currentRun.validations.length > 0 && (
          <ValidationList validations={currentRun.validations} />
        )}

        {/* ── Finalize + Download card ───────────────────────────── */}
        {currentRun && (
          <FinalizeCard
            currentRun={currentRun}
            fatalCount={fatalValidations.length}
            onFinalize={handleFinalize}
            onDownload={handleDownload}
            onDownloadReport={handleDownloadReport}
          />
        )}

        {/* ── Run history ─────────────────────────────────────────── */}
        {runs.length > 0 && (
          <RunHistoryCard
            runs={runs}
            selectedRunId={currentRun?.run.id}
            onSelectRun={async runId => {
              try {
                const detail = await creditReportAPI.getRun(runId);
                setCurrentRun(detail);
                setActiveBucket('ready');
                document
                  .getElementById('preview-section')
                  ?.scrollIntoView({ behavior: 'smooth' });
              } catch (e) {
                setError(e instanceof Error ? e.message : 'Failed to load run');
              }
            }}
          />
        )}
      </div>

      {/* ── MongoDB export instructions modal ──────────────────────── */}
      {showInstructions && <MongoInstructionsModal onClose={() => setShowInstructions(false)} />}
    </Layout>
  );
}

// ─── Subcomponents (inlined for Step 5; extracted later) ────────────────────
function defaultCycleMonth(): string {
  const d = new Date();
  d.setDate(1);
  d.setDate(d.getDate() - 1); // last day of previous month
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${yyyy}-${mm}-01`;
}

function StatusBanner({
  runs,
  currentRun,
}: {
  runs: RunSummary[];
  currentRun: RunDetail | null;
}) {
  const latestFinal = runs.find(r => r.status === 'final');
  const existingDraftsForCycle = currentRun
    ? runs.filter(
        r =>
          r.status === 'draft' &&
          r.cycle_month === currentRun.run.cycle_month &&
          r.id !== currentRun.run.id
      )
    : [];

  // Detect skipped-month: last finalized cycle is more than one month before
  // the current run's cycle.
  const skipNotice = useMemo(() => {
    if (!currentRun || !latestFinal) return null;
    const current = new Date(currentRun.run.cycle_month);
    const prior = new Date(latestFinal.cycle_month);
    if (isNaN(current.getTime()) || isNaN(prior.getTime())) return null;
    const months =
      (current.getFullYear() - prior.getFullYear()) * 12 +
      (current.getMonth() - prior.getMonth());
    if (months > 1) {
      return `You skipped ${months - 1} cycle${months - 1 === 1 ? '' : 's'} between ${formatDate(latestFinal.cycle_month)} and this run. Continuity is being pulled from the ${formatDate(latestFinal.cycle_month)} cycle.`;
    }
    return null;
  }, [currentRun, latestFinal]);

  return (
    <div className="space-y-3">
      <div className="bg-card p-6 rounded-lg shadow border border-border">
        <div className="flex items-start justify-between gap-6">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              {currentRun ? (
                <span
                  className={`px-3 py-1 rounded-full text-sm font-medium ${
                    currentRun.run.status === 'final'
                      ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
                      : currentRun.run.status === 'archived'
                      ? 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
                      : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
                  }`}
                >
                  {currentRun.run.status.toUpperCase()}
                </span>
              ) : (
                <span className="px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300">
                  NOT STARTED
                </span>
              )}
              <h2 className="text-xl font-semibold text-foreground">
                {currentRun
                  ? `Cycle ${currentRun.run.cycle_month}`
                  : 'No active cycle'}
              </h2>
            </div>
            {latestFinal ? (
              <p className="text-sm text-muted-foreground">
                Last finalized cycle: {formatDate(latestFinal.cycle_month)} —{' '}
                {latestFinal.ready_count} accounts reported
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                No prior finalized cycles. Upload your first CSVs below to begin.
              </p>
            )}
            {currentRun?.run.note && (
              <p className="text-xs text-muted-foreground mt-2 italic">
                Audit note: {currentRun.run.note}
              </p>
            )}
          </div>
        </div>
      </div>

      {skipNotice && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-sm text-amber-800 dark:text-amber-300">{skipNotice}</div>
        </div>
      )}

      {existingDraftsForCycle.length > 0 && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 flex items-start gap-3">
          <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-sm text-blue-800 dark:text-blue-300">
            {existingDraftsForCycle.length} other draft
            {existingDraftsForCycle.length === 1 ? '' : 's'} exist for this cycle.
            Use the run history panel at the bottom to switch between them.
          </div>
        </div>
      )}
    </div>
  );
}

function FileDropZone({
  label,
  file,
  onFileChange,
  hint,
}: {
  label: string;
  file: File | null;
  onFileChange: (f: File | null) => void;
  hint: string;
}) {
  return (
    <label className="block cursor-pointer">
      <span className="block text-sm font-medium text-foreground mb-1">{label}</span>
      <div
        className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
          file
            ? 'border-green-400 bg-green-50 dark:bg-green-900/20'
            : 'border-border hover:border-blue-400 bg-muted/20'
        }`}
      >
        {file ? (
          <div>
            <CheckCircle2 className="w-8 h-8 text-green-600 mx-auto mb-2" />
            <p className="text-sm font-medium text-foreground">{file.name}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {(file.size / 1024).toFixed(1)} KB
            </p>
          </div>
        ) : (
          <div>
            <Upload className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">Click to select</p>
            <p className="text-xs text-muted-foreground mt-1">{hint}</p>
          </div>
        )}
      </div>
      <input
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={e => onFileChange(e.target.files?.[0] ?? null)}
      />
    </label>
  );
}

function BucketTable({
  bucket,
  items,
  total,
  loading,
  isDraft,
  onSetBusinessFlag,
  onSetReviewDecision,
}: {
  bucket: BucketKey;
  items: RunItem[];
  total: number;
  loading: boolean;
  isDraft: boolean;
  onSetBusinessFlag: (dealId: string, isBusiness: boolean) => void;
  onSetReviewDecision: (
    dealId: string,
    decision: 'approve' | 'exclude' | 'defer',
    metro2_status_code?: string,
    fcra_dofi?: string,
    note?: string
  ) => void;
}) {
  if (loading) {
    return (
      <div className="py-12 text-center text-muted-foreground">Loading...</div>
    );
  }
  if (items.length === 0) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        No accounts in this bucket.
      </div>
    );
  }

  const headers =
    bucket === 'ready'
      ? ['Deal ID', 'Client name', 'Status', 'Loan amount', 'Balance', 'Opened', 'Actions']
      : bucket === 'review'
      ? ['Deal ID', 'Client name', 'Status', 'Days past due', 'Reason', 'Decision']
      : bucket === 'excluded'
      ? ['Deal ID', 'Client name', 'Status', 'Reason', 'Flag source', 'Actions']
      : ['Deal ID', 'Client name', 'Status', 'Last reported'];

  return (
    <div>
      <div className="text-sm text-muted-foreground mb-2">
        Showing {items.length} of {total}
      </div>
      <div className="overflow-x-auto border border-border rounded-lg">
        <table className="w-full">
          <thead className="bg-muted/50">
            <tr>
              {headers.map(h => (
                <th
                  key={h}
                  className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map(item => (
              <BucketRow
                key={item.id}
                bucket={bucket}
                item={item}
                isDraft={isDraft}
                onSetBusinessFlag={onSetBusinessFlag}
                onSetReviewDecision={onSetReviewDecision}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BucketRow({
  bucket,
  item,
  isDraft,
  onSetBusinessFlag,
  onSetReviewDecision,
}: {
  bucket: BucketKey;
  item: RunItem;
  isDraft: boolean;
  onSetBusinessFlag: (dealId: string, isBusiness: boolean) => void;
  onSetReviewDecision: (
    dealId: string,
    decision: 'approve' | 'exclude' | 'defer',
    metro2_status_code?: string,
    fcra_dofi?: string,
    note?: string
  ) => void;
}) {
  const src = item.source_row || {};
  const dealId = item.deal_id;
  const clientName = String(src.clientName ?? '');
  const statusName = String(src.statusName ?? '');
  const [expandedReview, setExpandedReview] = useState(false);

  if (bucket === 'ready') {
    const m2 = item.metro2_row || {};
    return (
      <tr className="hover:bg-muted/30 transition-colors">
        <td className="px-4 py-3 text-sm text-foreground font-mono">{dealId}</td>
        <td className="px-4 py-3 text-sm text-foreground">
          {clientName}
          {item.review_decision === 'approve' && (
            <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300">
              Auto-applied
            </span>
          )}
        </td>
        <td className="px-4 py-3 text-sm text-foreground">{statusName}</td>
        <td className="px-4 py-3 text-sm text-foreground">
          ${m2.HighestCreditOrOrigLoanAmt ?? '0'}
        </td>
        <td className="px-4 py-3 text-sm text-foreground">${m2.CurrentBalance ?? '0'}</td>
        <td className="px-4 py-3 text-sm text-foreground">{m2.DateOpened ?? ''}</td>
        <td className="px-4 py-3 text-sm">
          {isDraft && (
            <button
              onClick={() => {
                if (confirm(`Flag ${clientName} (${dealId}) as a business account?`)) {
                  onSetBusinessFlag(dealId, true);
                }
              }}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-muted hover:bg-muted/70 rounded border border-border"
              title="Move to excluded as a business entity"
            >
              <Building2 className="w-3 h-3" />
              Flag business
            </button>
          )}
        </td>
      </tr>
    );
  }

  if (bucket === 'review') {
    return (
      <>
        <tr className="hover:bg-muted/30 transition-colors">
          <td className="px-4 py-3 text-sm text-foreground font-mono">{dealId}</td>
          <td className="px-4 py-3 text-sm text-foreground">{clientName}</td>
          <td className="px-4 py-3 text-sm text-foreground">{statusName}</td>
          <td className="px-4 py-3 text-sm text-foreground">
            {String(src.daysPastDue ?? '')}
          </td>
          <td className="px-4 py-3 text-sm text-muted-foreground">{item.reason ?? ''}</td>
          <td className="px-4 py-3 text-sm">
            {isDraft ? (
              <button
                onClick={() => setExpandedReview(e => !e)}
                className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                {expandedReview ? 'Close' : 'Decide'}
              </button>
            ) : (
              <span className="text-xs text-muted-foreground">
                {item.review_decision ?? 'pending'}
              </span>
            )}
          </td>
        </tr>
        {expandedReview && isDraft && (
          <tr>
            <td colSpan={6} className="px-4 py-4 bg-muted/20 border-t border-border">
              <ReviewDecisionForm
                item={item}
                onSubmit={(decision, code, dofi, note) => {
                  setExpandedReview(false);
                  onSetReviewDecision(dealId, decision, code, dofi, note);
                }}
                onCancel={() => setExpandedReview(false)}
              />
            </td>
          </tr>
        )}
      </>
    );
  }

  if (bucket === 'excluded') {
    const wasBusiness = item.business_flag_source === 'auto' || item.business_flag_source === 'manual_on';
    return (
      <tr className="hover:bg-muted/30 transition-colors">
        <td className="px-4 py-3 text-sm text-foreground font-mono">{dealId}</td>
        <td className="px-4 py-3 text-sm text-foreground">{clientName}</td>
        <td className="px-4 py-3 text-sm text-foreground">{statusName}</td>
        <td className="px-4 py-3 text-sm text-muted-foreground">{item.reason ?? ''}</td>
        <td className="px-4 py-3 text-sm text-muted-foreground">
          {item.business_flag_source ?? '-'}
        </td>
        <td className="px-4 py-3 text-sm">
          {isDraft && wasBusiness && (
            <button
              onClick={() => {
                if (
                  confirm(
                    `Unflag ${clientName} (${dealId}) - mark as a consumer account?`
                  )
                ) {
                  onSetBusinessFlag(dealId, false);
                }
              }}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-muted hover:bg-muted/70 rounded border border-border"
              title="Override business detection and mark as consumer"
            >
              <User className="w-3 h-3" />
              Unflag
            </button>
          )}
        </td>
      </tr>
    );
  }

  // carried
  return (
    <tr className="hover:bg-muted/30 transition-colors">
      <td className="px-4 py-3 text-sm text-foreground font-mono">{dealId}</td>
      <td className="px-4 py-3 text-sm text-foreground">{clientName}</td>
      <td className="px-4 py-3 text-sm text-foreground">{statusName}</td>
      <td className="px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
        Missing from current upload
      </td>
    </tr>
  );
}

function ReviewDecisionForm({
  item,
  onSubmit,
  onCancel,
}: {
  item: RunItem;
  onSubmit: (
    decision: 'approve' | 'exclude' | 'defer',
    metro2_status_code?: string,
    fcra_dofi?: string,
    note?: string
  ) => void;
  onCancel: () => void;
}) {
  const [decision, setDecision] = useState<'approve' | 'exclude' | 'defer'>('approve');
  const [code, setCode] = useState(item.review_metro2_status_code ?? '');
  const [dofi, setDofi] = useState(item.review_fcra_dofi ?? '');
  const [note, setNote] = useState(item.review_note ?? '');
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const handleSave = () => {
    setErrMsg(null);
    if (decision === 'approve') {
      if (!code.trim()) {
        setErrMsg('Metro 2 status code is required when approving.');
        return;
      }
      if (dofi && !/^\d{8}$/.test(dofi.trim())) {
        setErrMsg('FCRA DOFI must be 8 digits (YYYYMMDD).');
        return;
      }
    }
    onSubmit(decision, code.trim() || undefined, dofi.trim() || undefined, note.trim() || undefined);
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {(['approve', 'exclude', 'defer'] as const).map(d => (
          <button
            key={d}
            onClick={() => setDecision(d)}
            className={`px-3 py-1.5 text-sm rounded border transition-colors flex items-center gap-1 ${
              decision === d
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-card text-foreground border-border hover:bg-muted/50'
            }`}
          >
            {d === 'approve' && <Check className="w-3 h-3" />}
            {d === 'exclude' && <Ban className="w-3 h-3" />}
            {d === 'defer' && <Clock className="w-3 h-3" />}
            {d.charAt(0).toUpperCase() + d.slice(1)}
          </button>
        ))}
      </div>

      {decision === 'approve' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-foreground mb-1">
              Metro 2 status code
              <span className="text-red-600">*</span>
            </label>
            <input
              type="text"
              value={code}
              onChange={e => setCode(e.target.value)}
              placeholder="e.g. 64, 94, 95, 97"
              className="w-full px-3 py-1.5 text-sm border border-input rounded bg-card text-foreground"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground mb-1">
              FCRA DOFI (YYYYMMDD)
            </label>
            <input
              type="text"
              value={dofi}
              onChange={e => setDofi(e.target.value)}
              placeholder="20251015"
              maxLength={8}
              className="w-full px-3 py-1.5 text-sm border border-input rounded bg-card text-foreground"
            />
          </div>
        </div>
      )}

      <div>
        <label className="block text-xs font-medium text-foreground mb-1">
          Note (optional)
        </label>
        <input
          type="text"
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="Context for the decision"
          className="w-full px-3 py-1.5 text-sm border border-input rounded bg-card text-foreground"
        />
      </div>

      {errMsg && (
        <div className="text-xs text-red-600">{errMsg}</div>
      )}

      <div className="flex gap-2 justify-end">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm bg-muted text-foreground rounded hover:bg-muted/70"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Save decision
        </button>
      </div>
    </div>
  );
}

function FinalizeCard({
  currentRun,
  fatalCount,
  onFinalize,
  onDownload,
  onDownloadReport,
}: {
  currentRun: RunDetail;
  fatalCount: number;
  onFinalize: (force: boolean, note?: string) => void;
  onDownload: (bucket: BucketKey) => void;
  onDownloadReport: () => void;
}) {
  const [note, setNote] = useState('');
  const [finalizing, setFinalizing] = useState(false);

  const isDraft = currentRun.run.status === 'draft';
  const isFinal = currentRun.run.status === 'final';

  const handleFinalizeClick = async (force: boolean) => {
    if (
      !confirm(
        force
          ? `Override ${fatalCount} FATAL warning(s) and finalize cycle ${currentRun.run.cycle_month}?`
          : `Finalize cycle ${currentRun.run.cycle_month}? This locks the run and writes cross-cycle state.`
      )
    ) {
      return;
    }
    setFinalizing(true);
    try {
      await onFinalize(force, note || undefined);
    } finally {
      setFinalizing(false);
    }
  };

  return (
    <div className="bg-card p-6 rounded-lg shadow border border-border">
      <h2 className="text-xl font-semibold text-foreground mb-1">
        3. Finalize and download
      </h2>
      <p className="text-sm text-muted-foreground mb-4">
        {isFinal
          ? 'This run is finalized. Re-download any bucket CSV or the summary report below.'
          : 'Lock the cycle and persist cross-cycle state (business flags, review decisions, continuity).'}
      </p>

      {isDraft && (
        <div className="space-y-3 mb-5">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              Audit note (optional)
            </label>
            <input
              type="text"
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="e.g. Sent to Switch Labs by Mariana on 2026-04-02"
              className="w-full px-4 py-2 border border-input rounded-lg bg-card text-foreground"
            />
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => handleFinalizeClick(false)}
              disabled={finalizing || fatalCount > 0}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              title={
                fatalCount > 0
                  ? `Resolve ${fatalCount} FATAL warning(s) first, or click "Override" below.`
                  : 'Finalize and lock this cycle'
              }
            >
              <Lock className="w-4 h-4" />
              {finalizing ? 'Finalizing...' : 'Finalize and lock cycle'}
            </button>
            {fatalCount > 0 && (
              <button
                onClick={() => handleFinalizeClick(true)}
                disabled={finalizing}
                className="px-5 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center gap-2"
                title={`Override ${fatalCount} FATAL warning(s) and finalize anyway`}
              >
                <AlertCircle className="w-4 h-4" />
                Override and finalize
              </button>
            )}
          </div>
          {fatalCount > 0 && (
            <p className="text-sm text-red-600">
              {fatalCount} FATAL warning(s) present. Review them above before finalizing.
            </p>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          onClick={() => onDownload('ready')}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          Metro 2 ready CSV
        </button>
        <button
          onClick={() => onDownload('review')}
          className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          Review CSV
        </button>
        <button
          onClick={() => onDownload('excluded')}
          className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          Excluded CSV
        </button>
        <button
          onClick={onDownloadReport}
          className="px-4 py-2 bg-card border border-border text-foreground rounded-lg hover:bg-muted/50 transition-colors flex items-center gap-2"
        >
          <FileText className="w-4 h-4" />
          Summary report (.txt)
        </button>
      </div>
    </div>
  );
}

function ValidationList({ validations }: { validations: Validation[] }) {
  const iconFor = (sev: string) => {
    if (sev === 'FATAL') return <XCircle className="w-5 h-5 text-red-600" />;
    if (sev === 'WARNING') return <AlertCircle className="w-5 h-5 text-amber-600" />;
    return <Info className="w-5 h-5 text-blue-600" />;
  };
  const colorFor = (sev: string) => {
    if (sev === 'FATAL') return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800';
    if (sev === 'WARNING') return 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800';
    return 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800';
  };
  return (
    <div className="bg-card p-6 rounded-lg shadow border border-border">
      <h2 className="text-xl font-semibold text-foreground mb-4">Validation findings</h2>
      <div className="space-y-2">
        {validations.map((v, i) => (
          <div
            key={i}
            className={`border rounded-lg p-3 flex items-start gap-3 ${colorFor(v.severity)}`}
          >
            {iconFor(v.severity)}
            <div className="flex-1 text-sm">
              <div className="font-medium text-foreground">
                [{v.severity}] {v.code}
              </div>
              <div className="text-muted-foreground mt-0.5">{v.message}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RunHistoryCard({
  runs,
  selectedRunId,
  onSelectRun,
}: {
  runs: RunSummary[];
  selectedRunId?: string;
  onSelectRun: (runId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="bg-card p-6 rounded-lg shadow border border-border">
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex items-center justify-between w-full text-left"
      >
        <div>
          <h2 className="text-xl font-semibold text-foreground">Run history</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {runs.length} recent run{runs.length === 1 ? '' : 's'}. Click any row
            to view it in the preview above.
          </p>
        </div>
        <span className="text-sm text-blue-600 hover:text-blue-700">
          {expanded ? 'Collapse' : 'Expand'}
        </span>
      </button>
      {expanded && (
        <div className="mt-4 overflow-x-auto border border-border rounded-lg">
          <table className="w-full">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                  Cycle
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                  Ready
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                  Review
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                  Excluded
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                  Carried
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                  Finalized
                </th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {runs.map(run => {
                const isSelected = run.id === selectedRunId;
                return (
                  <tr
                    key={run.id}
                    className={`transition-colors ${
                      isSelected ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-muted/30'
                    }`}
                  >
                    <td className="px-4 py-3 text-sm text-foreground font-medium">
                      {formatDate(run.cycle_month)}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          run.status === 'final'
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300'
                            : run.status === 'archived'
                            ? 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-400'
                            : 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300'
                        }`}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-foreground">{run.ready_count}</td>
                    <td className="px-4 py-3 text-sm text-foreground">{run.review_count}</td>
                    <td className="px-4 py-3 text-sm text-foreground">{run.excluded_count}</td>
                    <td className="px-4 py-3 text-sm text-foreground">
                      {run.carried_over_count}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {run.finalized_at
                        ? new Date(run.finalized_at).toLocaleString()
                        : '-'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => onSelectRun(run.id)}
                        className="text-xs text-blue-600 hover:text-blue-700 underline"
                      >
                        {isSelected ? 'Selected' : 'View'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MongoInstructionsModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black bg-opacity-50" onClick={onClose} />
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-card rounded-lg shadow-xl max-w-2xl w-full p-6">
          <div className="flex items-start justify-between mb-4">
            <h3 className="text-xl font-semibold text-foreground">
              How to export from MongoDB
            </h3>
            <button
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Run these two commands in the MongoDB shell, or use MongoDB Compass to
            export each collection as CSV.
          </p>
          <div className="bg-muted/30 rounded-lg p-4 font-mono text-xs text-foreground overflow-x-auto">
            <div className="mb-4">
              <div className="text-muted-foreground mb-1"># Deals collection</div>
              mongoexport --db=&lt;your_db&gt; --collection=deals \<br />
              &nbsp;&nbsp;--type=csv --fields=... \<br />
              &nbsp;&nbsp;--out=kingdomautofinance_Deal.csv
            </div>
            <div>
              <div className="text-muted-foreground mb-1"># Addresses collection</div>
              mongoexport --db=&lt;your_db&gt; --collection=dealaddresses \<br />
              &nbsp;&nbsp;--type=csv --fields=_id,address,address2,city,state,zip,postalCode \<br />
              &nbsp;&nbsp;--out=kingdomautofinance_Address.csv
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-4">
            Once both files are saved to your laptop, drop them into the Upload
            card and click <span className="font-medium">Process upload</span>.
          </p>
          <div className="mt-6 flex justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Got it
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
