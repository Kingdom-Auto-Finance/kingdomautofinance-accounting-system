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
  Trash2,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Eye,
  Minus,
  Plus,
} from 'lucide-react';

// Required Metro 2 fields checked per-row so the UI can flag rows with blanks.
const REQUIRED_METRO2_FIELDS = [
  'ConsumerAccountNumber',
  'DateOpened',
  'HighestCreditOrOrigLoanAmt',
  'AccountStatus',
  'CurrentBalance',
  'DateOfAccountInfo',
  'Surname',
  'FirstName',
  'SSN',
  'Address1',
  'City',
  'State',
  'PostalCode',
];

type BucketKey = 'ready' | 'review' | 'excluded' | 'carried' | 'skipped';

const BUCKET_LABELS: Record<BucketKey, string> = {
  ready: 'Ready',
  review: 'Needs Review',
  excluded: 'Excluded',
  carried: 'Carried over',
  skipped: 'Skipped this cycle',
};

const BUCKET_COLORS: Record<BucketKey, string> = {
  ready: 'text-green-700 bg-green-100 dark:bg-green-900/30 dark:text-green-300',
  review: 'text-amber-700 bg-amber-100 dark:bg-amber-900/30 dark:text-amber-300',
  excluded: 'text-gray-700 bg-gray-100 dark:bg-gray-800 dark:text-gray-300',
  carried: 'text-blue-700 bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300',
  skipped: 'text-purple-700 bg-purple-100 dark:bg-purple-900/30 dark:text-purple-300',
};

// Curated Metro 2 status codes for the review decision form's hybrid combobox.
// Operators can type freely, or pick from this list; the description shown
// below the input updates live as they type or select.
// Full Metro 2 code reference: https://www.consumerfinance.gov/rules-policy/guidance/
const METRO2_STATUS_CODES: { code: string; description: string }[] = [
  { code: '05', description: 'Account transferred to another lender' },
  { code: '11', description: 'Current account, paid as agreed' },
  { code: '13', description: 'Paid or closed account, zero balance' },
  { code: '61', description: 'Paid in full; was a voluntary surrender' },
  { code: '62', description: 'Paid in full; was a collection account' },
  { code: '63', description: 'Paid in full; was a repossession' },
  { code: '64', description: 'Paid in full; was a charge-off' },
  { code: '65', description: 'Paid in full; was a bankruptcy' },
  { code: '71', description: 'Account 30 days past due' },
  { code: '78', description: 'Account 60 days past due' },
  { code: '80', description: 'Account 90 days past due' },
  { code: '82', description: 'Account 120 days past due' },
  { code: '83', description: 'Account 150 days past due' },
  { code: '84', description: 'Account 180 days past due' },
  { code: '93', description: 'Account assigned to internal or external collections' },
  { code: '94', description: 'Claim filed with government guarantor' },
  { code: '95', description: 'Voluntary surrender' },
  { code: '96', description: 'Merchandise was repossessed' },
  { code: '97', description: 'Unpaid balance reported as a loss (charge-off)' },
  { code: 'DA', description: 'Delete entire account (admin use only)' },
];

type ToastItem = {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
};
let _toastIdCounter = 0;

export default function CreditReportsPage() {
  // ── Global state ─────────────────────────────────────────────────────
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [currentRun, setCurrentRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback(
    (message: string, type: ToastItem['type'] = 'info') => {
      const id = ++_toastIdCounter;
      setToasts(prev => [...prev, { id, message, type }]);
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, 4000);
    },
    []
  );

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
  // MongoDB export instructions modal removed per user request.
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10000); // "All" by default
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  // Filter by deal_ids from a validation finding drilldown
  const [affectedDealIds, setAffectedDealIds] = useState<string[] | null>(null);
  const [affectedFindingLabel, setAffectedFindingLabel] = useState<string | null>(null);

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

  // ── Reload items whenever active bucket, run, page, size, sort, or filter changes ──
  useEffect(() => {
    if (currentRun) {
      loadItems(
        currentRun.run.id,
        activeBucket,
        searchQuery,
        page,
        pageSize,
        sortKey,
        sortDir,
        affectedDealIds
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    currentRun?.run.id,
    activeBucket,
    page,
    pageSize,
    sortKey,
    sortDir,
    affectedDealIds,
  ]);

  // Reset to page 1 whenever the bucket switches so we don't land past the end.
  useEffect(() => {
    setPage(1);
    setSortKey(null);
  }, [activeBucket, currentRun?.run.id]);

  const loadItems = useCallback(
    async (
      runId: string,
      bucket: BucketKey,
      query: string,
      pageArg: number,
      pageSizeArg: number,
      sortKeyArg: string | null,
      sortDirArg: 'asc' | 'desc',
      dealIdsFilter: string[] | null
    ) => {
      setBucketLoading(true);
      try {
        const resp = await creditReportAPI.listItems(runId, {
          bucket,
          q: query || undefined,
          page: pageArg,
          page_size: pageSizeArg,
          order_by: sortKeyArg || undefined,
          order_dir: sortDirArg,
          deal_ids: dealIdsFilter || undefined,
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

  // ── Search handler (reset to page 1 on query change) ─────────────────
  const handleSearchChange = (val: string) => {
    setSearchQuery(val);
    setPage(1);
    if (currentRun) {
      loadItems(
        currentRun.run.id,
        activeBucket,
        val,
        1,
        pageSize,
        sortKey,
        sortDir,
        affectedDealIds
      );
    }
  };

  // ── Sort handler (toggles direction on repeated clicks) ──────────────
  // Sort is applied server-side across the full dataset; the useEffect on
  // sortKey/sortDir automatically re-fetches the page when either changes.
  const handleSortClick = (key: string) => {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
    // Reset to page 1 so the first sorted results land on top.
    setPage(1);
  };

  // ── Affected-rows drilldown from validation findings ────────────────
  const handleShowAffectedRows = (dealIds: string[], label: string) => {
    setAffectedDealIds(dealIds);
    setAffectedFindingLabel(label);
    setActiveBucket('ready');
    setPage(1);
    setSortKey(null);
    setTimeout(() => {
      document
        .getElementById('preview-section')
        ?.scrollIntoView({ behavior: 'smooth' });
    }, 50);
  };

  const handleClearAffectedFilter = () => {
    setAffectedDealIds(null);
    setAffectedFindingLabel(null);
    setPage(1);
  };

  // ── Decision handlers ────────────────────────────────────────────────
  const refreshAfterMutation = async () => {
    if (!currentRun) return;
    // Reload the run detail (so counts refresh) and the current bucket list.
    const detail = await creditReportAPI.getRun(currentRun.run.id);
    setCurrentRun(detail);
    loadItems(
      detail.run.id,
      activeBucket,
      searchQuery,
      page,
      pageSize,
      sortKey,
      sortDir,
      affectedDealIds
    );
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
    decision: 'approve' | 'exclude' | 'defer' | 'skip',
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
      loadItems(
        detail.run.id,
        activeBucket,
        searchQuery,
        page,
        pageSize,
        sortKey,
        sortDir,
        affectedDealIds
      );
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
      skipped: r?.skipped_count ?? 0,
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
          <a
            href="/credit-reports/metro2"
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 shadow"
          >
            <FileText className="w-4 h-4" />
            Open Metro 2 Platform
          </a>
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
        <CollapsibleSection
          title="1. Upload CSVs"
          subtitle="Export deals + dealaddresses from MongoDB and upload both files here."
          defaultOpen={false}
        >

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

          <div className="flex items-end gap-4 flex-wrap">
            <div className="w-48">
              <label className="block text-sm font-medium text-foreground mb-1">
                Cycle month
              </label>
              <input
                type="month"
                value={cycleMonth.slice(0, 7)}
                onChange={e => setCycleMonth(e.target.value + '-01')}
                className="w-full px-3 py-2 border border-input rounded-lg focus:ring-2 focus:ring-blue-500 bg-card text-foreground [color-scheme:dark]"
              />
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
        </CollapsibleSection>

        {/* ── Preview section ────────────────────────────────────── */}
        {currentRun && (
          <div id="preview-section">
          <CollapsibleSection
            title="2. Review accounts"
            subtitle={`Cycle ${currentRun.run.cycle_month} - Status: ${currentRun.run.status}`}
          >
            <div className="flex items-center justify-between mb-4">
              <div></div>
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

            {/* Affected-rows filter chip (shown when drilling down from a validation finding) */}
            {affectedDealIds && (
              <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                <Info className="w-4 h-4 text-blue-600 flex-shrink-0" />
                <span className="text-sm text-blue-800 dark:text-blue-300 flex-1">
                  Filtered by validation finding: <strong>{affectedFindingLabel}</strong>{' '}
                  ({affectedDealIds.length} rows)
                </span>
                <button
                  onClick={handleClearAffectedFilter}
                  className="text-xs text-blue-600 hover:text-blue-800 underline"
                >
                  Clear filter
                </button>
              </div>
            )}

            {/* Items table */}
            <BucketTable
              bucket={activeBucket}
              items={bucketItems}
              total={bucketTotal}
              loading={bucketLoading}
              isDraft={currentRun.run.status === 'draft'}
              page={page}
              pageSize={pageSize}
              sortKey={sortKey}
              sortDir={sortDir}
              onSortClick={handleSortClick}
              onPageChange={setPage}
              onPageSizeChange={size => {
                setPageSize(size);
                setPage(1);
              }}
              onSetBusinessFlag={handleSetBusinessFlag}
              onSetReviewDecision={handleSetReviewDecision}
            />
          </CollapsibleSection>
          </div>
        )}

        {/* ── Validation panel ───────────────────────────────────── */}
        {currentRun && currentRun.validations.length > 0 && (
          <ValidationList
            validations={currentRun.validations}
            onShowAffectedRows={handleShowAffectedRows}
          />
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
            onDeleteDraft={async runId => {
              try {
                await creditReportAPI.deleteDraft(runId);
                showToast('Draft deleted successfully', 'success');
                if (currentRun?.run.id === runId) {
                  setCurrentRun(null);
                }
                await loadRuns();
              } catch (e) {
                showToast(
                  e instanceof Error ? e.message : 'Failed to delete draft',
                  'error'
                );
              }
            }}
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

        {/* ── Rules reference ─────────────────────────────────────── */}
        <RulesReferenceCard />
      </div>

      {/* ── Toast notifications ──────────────────────────────────────── */}
      {toasts.length > 0 && (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
          {toasts.map(t => (
            <div
              key={t.id}
              className={`px-4 py-3 rounded-lg shadow-lg border text-sm font-medium animate-in slide-in-from-right-5 ${
                t.type === 'success'
                  ? 'bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-800 text-green-800 dark:text-green-300'
                  : t.type === 'error'
                  ? 'bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800 text-red-800 dark:text-red-300'
                  : 'bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-300'
              }`}
            >
              <div className="flex items-center gap-2">
                {t.type === 'success' && <CheckCircle2 className="w-4 h-4 flex-shrink-0" />}
                {t.type === 'error' && <XCircle className="w-4 h-4 flex-shrink-0" />}
                {t.type === 'info' && <Info className="w-4 h-4 flex-shrink-0" />}
                <span>{t.message}</span>
                <button
                  onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
                  className="ml-auto opacity-60 hover:opacity-100"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Layout>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────
/** Format a Metro 2 YYYYMMDD string as MM/DD/YYYY for UI display. */
function formatMetro2Date(value: any): string {
  if (value === null || value === undefined || value === '') return '';
  const s = String(value).trim();
  if (!/^\d{8}$/.test(s)) return s;
  return `${s.slice(4, 6)}/${s.slice(6, 8)}/${s.slice(0, 4)}`;
}

/** Format a whole-dollar amount string like "12345" as "$12,345". */
function formatWholeDollar(value: any): string {
  if (value === null || value === undefined || value === '') return '$0';
  const n = Number(value);
  if (!Number.isFinite(n)) return `$${value}`;
  return `$${n.toLocaleString('en-US')}`;
}

/** Check a Ready row's metro2_row for blank required fields. Returns the list of field names. */
function getBlankRequiredFields(item: RunItem): string[] {
  if (!item.metro2_row) return [];
  return REQUIRED_METRO2_FIELDS.filter(f => {
    const v = item.metro2_row?.[f];
    return v === null || v === undefined || String(v).trim() === '';
  });
}

/** Collapsible section wrapper for the single-scroll layout. */
function CollapsibleSection({
  title,
  subtitle,
  defaultOpen = true,
  children,
}: {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-card rounded-lg shadow border border-border overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-muted/30 transition-colors"
      >
        <div>
          <h2 className="text-xl font-semibold text-foreground">{title}</h2>
          {subtitle && (
            <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>
          )}
        </div>
        <div className="flex-shrink-0 p-1 rounded hover:bg-muted">
          {open ? (
            <Minus className="w-4 h-4 text-muted-foreground" />
          ) : (
            <Plus className="w-4 h-4 text-muted-foreground" />
          )}
        </div>
      </button>
      {open && <div className="px-6 pb-6">{children}</div>}
    </div>
  );
}

// ─── Subcomponents ──────────────────────────────────────────────────────────
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

type ColumnDef = {
  label: string;
  sortKey: string | null; // null = unsortable (e.g. Actions column)
};

const COLUMN_DEFS: Record<BucketKey, ColumnDef[]> = {
  ready: [
    { label: 'Deal ID', sortKey: 'deal_id' },
    { label: 'Client name', sortKey: 'client_name' },
    { label: 'Status', sortKey: 'status_name' },
    { label: 'Loan amount', sortKey: 'loan_amount' },
    { label: 'Balance', sortKey: 'current_balance' },
    { label: 'Loan date', sortKey: 'date_opened' },
    { label: 'Actions', sortKey: null },
  ],
  review: [
    { label: 'Deal ID', sortKey: 'deal_id' },
    { label: 'Client name', sortKey: 'client_name' },
    { label: 'Status', sortKey: 'status_name' },
    { label: 'Days past due', sortKey: 'days_past_due' },
    { label: 'Reason', sortKey: 'reason' },
    { label: 'Decision', sortKey: null },
  ],
  excluded: [
    { label: 'Deal ID', sortKey: 'deal_id' },
    { label: 'Client name', sortKey: 'client_name' },
    { label: 'Status', sortKey: 'status_name' },
    { label: 'Reason', sortKey: 'reason' },
    { label: 'Flag source', sortKey: 'business_flag_source' },
    { label: 'Actions', sortKey: null },
  ],
  carried: [
    { label: 'Deal ID', sortKey: 'deal_id' },
    { label: 'Client name', sortKey: 'client_name' },
    { label: 'Status', sortKey: 'status_name' },
    { label: 'Last reported', sortKey: null },
  ],
  skipped: [
    { label: 'Deal ID', sortKey: 'deal_id' },
    { label: 'Client name', sortKey: 'client_name' },
    { label: 'Status', sortKey: 'status_name' },
    { label: 'Reason', sortKey: 'reason' },
    { label: 'Actions', sortKey: null },
  ],
};

function BucketTable({
  bucket,
  items,
  total,
  loading,
  isDraft,
  page,
  pageSize,
  sortKey,
  sortDir,
  onSortClick,
  onPageChange,
  onPageSizeChange,
  onSetBusinessFlag,
  onSetReviewDecision,
}: {
  bucket: BucketKey;
  items: RunItem[];
  total: number;
  loading: boolean;
  isDraft: boolean;
  page: number;
  pageSize: number;
  sortKey: string | null;
  sortDir: 'asc' | 'desc';
  onSortClick: (key: string) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onSetBusinessFlag: (dealId: string, isBusiness: boolean) => void;
  onSetReviewDecision: (
    dealId: string,
    decision: 'approve' | 'exclude' | 'defer' | 'skip',
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

  const columns = COLUMN_DEFS[bucket];
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const rangeStart = (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);

  return (
    <div>
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="text-sm text-muted-foreground">
          Showing {rangeStart}–{rangeEnd} of {total}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <label className="text-muted-foreground">Rows per page:</label>
          <select
            value={pageSize}
            onChange={e => onPageSizeChange(Number(e.target.value))}
            className="px-2 py-1 border border-input rounded bg-card text-foreground"
          >
            {[50, 100, 200, 500].map(n => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
            <option value={10000}>All</option>
          </select>
        </div>
      </div>
      <div className="overflow-x-auto border border-border rounded-lg">
        <table className="w-full">
          <thead className="bg-muted/50">
            <tr>
              {columns.map(col => {
                const isSorted = col.sortKey && sortKey === col.sortKey;
                return (
                  <th
                    key={col.label}
                    onClick={() => col.sortKey && onSortClick(col.sortKey)}
                    className={`px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase ${
                      col.sortKey ? 'cursor-pointer select-none hover:bg-muted' : ''
                    }`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.label}
                      {isSorted && (
                        <span aria-hidden="true">
                          {sortDir === 'asc' ? '▲' : '▼'}
                        </span>
                      )}
                    </span>
                  </th>
                );
              })}
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
      {totalPages > 1 && (
        <div className="mt-3 flex items-center justify-end gap-2 text-sm">
          <button
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="px-3 py-1.5 border border-border rounded bg-card text-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1.5 border border-border rounded bg-card text-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
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
    decision: 'approve' | 'exclude' | 'defer' | 'skip',
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
    const blanks = getBlankRequiredFields(item);
    const hasBlanks = blanks.length > 0;
    return (
      <tr className={`transition-colors ${hasBlanks ? 'bg-amber-50/50 dark:bg-amber-900/10 hover:bg-amber-100/50' : 'hover:bg-muted/30'}`}>
        <td className="px-4 py-3 text-sm text-foreground font-mono">
          {hasBlanks && (
            <span title={`Missing: ${blanks.join(', ')}`}>
              <AlertTriangle className="w-4 h-4 text-amber-600 inline-block mr-1" />
            </span>
          )}
          {dealId}
        </td>
        <td className="px-4 py-3 text-sm text-foreground">
          {clientName}
          {item.review_decision === 'approve' && (
            <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300">
              Auto-applied
            </span>
          )}
          {hasBlanks && (
            <span
              className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300"
              title={blanks.join(', ')}
            >
              {blanks.length} blank field{blanks.length > 1 ? 's' : ''}
            </span>
          )}
        </td>
        <td className="px-4 py-3 text-sm text-foreground">{statusName}</td>
        <td className="px-4 py-3 text-sm text-foreground">
          {formatWholeDollar(m2.HighestCreditOrOrigLoanAmt)}
        </td>
        <td className="px-4 py-3 text-sm text-foreground">
          {formatWholeDollar(m2.CurrentBalance)}
        </td>
        <td className="px-4 py-3 text-sm text-foreground">
          {formatMetro2Date(m2.DateOpened)}
        </td>
        <td className="px-4 py-3 text-sm">
          {isDraft && (
            <div className="flex flex-wrap gap-1">
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
              <button
                onClick={() => {
                  if (
                    confirm(
                      `Skip ${clientName} (${dealId}) this cycle? It will come back for review next cycle.`
                    )
                  ) {
                    onSetReviewDecision(dealId, 'skip');
                  }
                }}
                className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300 hover:bg-purple-200 rounded border border-purple-300 dark:border-purple-700"
                title="Remove from this cycle; will be reviewed next cycle"
              >
                <Clock className="w-3 h-3" />
                Skip
              </button>
            </div>
          )}
        </td>
      </tr>
    );
  }

  if (bucket === 'skipped') {
    return (
      <tr className="hover:bg-muted/30 transition-colors">
        <td className="px-4 py-3 text-sm text-foreground font-mono">{dealId}</td>
        <td className="px-4 py-3 text-sm text-foreground">{clientName}</td>
        <td className="px-4 py-3 text-sm text-foreground">{statusName}</td>
        <td className="px-4 py-3 text-sm text-muted-foreground">{item.reason ?? ''}</td>
        <td className="px-4 py-3 text-sm text-muted-foreground italic">
          Will re-appear in Needs Review next cycle
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
    decision: 'approve' | 'exclude' | 'defer' | 'skip',
    metro2_status_code?: string,
    fcra_dofi?: string,
    note?: string
  ) => void;
  onCancel: () => void;
}) {
  const [decision, setDecision] = useState<'approve' | 'exclude' | 'defer' | 'skip'>(
    'approve'
  );
  const [code, setCode] = useState(item.review_metro2_status_code ?? '');
  const [dofi, setDofi] = useState(item.review_fcra_dofi ?? '');
  const [note, setNote] = useState(item.review_note ?? '');
  const [errMsg, setErrMsg] = useState<string | null>(null);

  // Look up the description for the currently-entered code (live).
  const codeDescription = useMemo(() => {
    const trimmed = code.trim().toUpperCase();
    if (!trimmed) return null;
    const match = METRO2_STATUS_CODES.find(c => c.code.toUpperCase() === trimmed);
    return match?.description ?? 'Custom code (not in the curated list)';
  }, [code]);

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
    onSubmit(
      decision,
      code.trim() || undefined,
      dofi.trim() || undefined,
      note.trim() || undefined
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {(['approve', 'exclude', 'defer', 'skip'] as const).map(d => (
          <button
            key={d}
            onClick={() => setDecision(d)}
            className={`px-3 py-1.5 text-sm rounded border transition-colors flex items-center gap-1 ${
              decision === d
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-card text-foreground border-border hover:bg-muted/50'
            }`}
            title={
              d === 'skip'
                ? 'Skip this cycle - will come back for review next cycle'
                : undefined
            }
          >
            {d === 'approve' && <Check className="w-3 h-3" />}
            {d === 'exclude' && <Ban className="w-3 h-3" />}
            {d === 'defer' && <Clock className="w-3 h-3" />}
            {d === 'skip' && <Clock className="w-3 h-3" />}
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
              list="metro2-status-codes"
              value={code}
              onChange={e => setCode(e.target.value)}
              placeholder="Type or pick - e.g. 95"
              className="w-full px-3 py-1.5 text-sm border border-input rounded bg-card text-foreground"
              autoComplete="off"
            />
            <datalist id="metro2-status-codes">
              {METRO2_STATUS_CODES.map(c => (
                <option key={c.code} value={c.code}>
                  {c.description}
                </option>
              ))}
            </datalist>
            {codeDescription && (
              <p className="text-xs text-muted-foreground mt-1 italic">
                {codeDescription}
              </p>
            )}
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

      {decision === 'skip' && (
        <div className="text-xs text-muted-foreground bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 rounded p-2">
          This account will be removed from the current cycle's Metro 2 file and
          automatically placed in the Needs Review queue on the next cycle,
          regardless of its MongoDB status at that time.
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

  const subtitle = isFinal
    ? 'This run is finalized. Re-download any bucket CSV or the summary report below.'
    : 'Lock the cycle and persist cross-cycle state (business flags, review decisions, continuity).';

  return (
    <CollapsibleSection title="3. Finalize and download" subtitle={subtitle}>

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
    </CollapsibleSection>
  );
}

function ValidationList({
  validations,
  onShowAffectedRows,
}: {
  validations: Validation[];
  onShowAffectedRows: (dealIds: string[], label: string) => void;
}) {
  const fatalCount = validations.filter(v => v.severity === 'FATAL').length;
  const warnCount = validations.filter(v => v.severity === 'WARNING').length;
  const subtitle = [
    fatalCount > 0 ? `${fatalCount} fatal` : '',
    warnCount > 0 ? `${warnCount} warning${warnCount > 1 ? 's' : ''}` : '',
    `${validations.length} total`,
  ]
    .filter(Boolean)
    .join(', ');

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
    <CollapsibleSection title="Validation findings" subtitle={subtitle}>
      <div className="space-y-2">
        {validations.map((v, i) => {
          const dealIds = v.affected_deal_ids ?? [];
          const hasDrilldown = dealIds.length > 0;
          return (
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
                {hasDrilldown && (
                  <button
                    onClick={() =>
                      onShowAffectedRows(dealIds, `${v.code} (${v.message})`)
                    }
                    className="mt-2 text-xs px-2 py-1 rounded border border-border bg-card hover:bg-muted/50 transition-colors font-medium"
                  >
                    Show {dealIds.length} affected row{dealIds.length === 1 ? '' : 's'}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </CollapsibleSection>
  );
}

function RunHistoryCard({
  runs,
  selectedRunId,
  onDeleteDraft,
  onSelectRun,
}: {
  runs: RunSummary[];
  selectedRunId?: string;
  onDeleteDraft: (runId: string) => void;
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
        <div className="p-1 rounded hover:bg-muted">
          {expanded ? (
            <Minus className="w-4 h-4 text-muted-foreground" />
          ) : (
            <Plus className="w-4 h-4 text-muted-foreground" />
          )}
        </div>
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
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => onSelectRun(run.id)}
                          className={`p-1 rounded transition-colors ${
                            isSelected
                              ? 'text-green-600 bg-green-100 dark:bg-green-900/30'
                              : 'text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900/30'
                          }`}
                          title={isSelected ? 'Currently selected' : 'View this run'}
                        >
                          {isSelected ? (
                            <Check className="w-4 h-4" />
                          ) : (
                            <Eye className="w-4 h-4" />
                          )}
                        </button>
                        {run.status === 'draft' && (
                          <button
                            onClick={() => {
                              if (
                                confirm(
                                  `Delete draft for cycle ${run.cycle_month}? This cannot be undone.`
                                )
                              ) {
                                onDeleteDraft(run.id);
                              }
                            }}
                            className="text-xs text-red-600 hover:text-red-700 flex items-center gap-0.5"
                            title="Delete this draft"
                          >
                            <Trash2 className="w-3 h-3" />
                            Delete
                          </button>
                        )}
                      </div>
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

function RulesReferenceCard() {
  const [expanded, setExpanded] = useState(false);
  const [rules, setRules] = useState<Awaited<
    ReturnType<typeof creditReportAPI.getRules>
  > | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    if (expanded && !rules && !loadErr) {
      creditReportAPI
        .getRules()
        .then(setRules)
        .catch(e =>
          setLoadErr(e instanceof Error ? e.message : 'Failed to load rules')
        );
    }
  }, [expanded, rules, loadErr]);

  return (
    <div className="bg-card p-6 rounded-lg shadow border border-border">
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex items-center justify-between w-full text-left"
      >
        <div>
          <h2 className="text-xl font-semibold text-foreground">
            Metro 2 rules reference
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            The business rules, status enums, and field mappings currently used
            by the engine. Read-only in v1.
          </p>
        </div>
        <div className="p-1 rounded hover:bg-muted">
          {expanded ? (
            <Minus className="w-4 h-4 text-muted-foreground" />
          ) : (
            <Plus className="w-4 h-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-5 space-y-5">
          {loadErr && (
            <div className="text-sm text-red-600">{loadErr}</div>
          )}
          {!rules && !loadErr && (
            <div className="text-sm text-muted-foreground">Loading rules...</div>
          )}
          {rules && (
            <>
              <RuleSection
                title="Experian configuration"
                description="Subscriber code and fixed-policy constants sent on every Metro 2 row."
                pairs={Object.entries(rules.experian_config).map(([k, v]) => [
                  k.replace(/_/g, ' '),
                  v,
                ])}
              />

              <RuleSection
                title="Status buckets"
                description="Which MongoDB statusName values land in which Metro 2 bucket."
              >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <RulePillList
                    label="Excluded from reporting"
                    color="gray"
                    values={rules.status_buckets.excluded}
                  />
                  <RulePillList
                    label="Needs review"
                    color="amber"
                    values={rules.status_buckets.review}
                  />
                  <RulePillList
                    label="Reported as status 11 (Current)"
                    color="green"
                    values={rules.status_buckets.active_reported_as_11}
                  />
                  <RulePillList
                    label="Reported as status 13 (Paid/closed)"
                    color="blue"
                    values={rules.status_buckets.closed_reported_as_13}
                  />
                </div>
              </RuleSection>

              <RuleSection
                title="Business-name detection regex"
                description="Any client name matching this pattern is auto-flagged as a business entity and excluded. Team members can override per account from the Ready / Excluded tabs above."
              >
                <div className="font-mono text-xs bg-muted/30 rounded p-3 break-all">
                  {rules.business_pattern}
                </div>
              </RuleSection>

              <RuleSection
                title="Payment frequency mapping"
                description="MongoDB 'frequency' value → Metro 2 TermsFrequency code."
              >
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {Object.entries(rules.frequency_map).map(([k, v]) => (
                    <div
                      key={k}
                      className="px-3 py-2 border border-border rounded bg-muted/20 text-sm"
                    >
                      <div className="font-medium text-foreground">{k}</div>
                      <div className="text-muted-foreground text-xs">
                        Metro 2 code: <span className="font-mono">{v.metro2_code}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </RuleSection>

              <RuleSection
                title="Address CSV column candidates"
                description="The uploader tries each candidate column name in order and picks the first one that exists in your CSV. Extend these lists in the backend if your mongoexport uses a name not listed."
              >
                <div className="space-y-2">
                  {Object.entries(rules.address_field_candidates).map(
                    ([internal, candidates]) => (
                      <div key={internal} className="flex items-start gap-3">
                        <div className="w-32 flex-shrink-0 font-medium text-foreground text-sm">
                          {internal}
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {candidates.map(c => (
                            <span
                              key={c}
                              className="px-2 py-0.5 text-xs bg-muted rounded border border-border font-mono"
                            >
                              {c}
                            </span>
                          ))}
                        </div>
                      </div>
                    )
                  )}
                </div>
              </RuleSection>

              <div className="text-xs text-muted-foreground border-t border-border pt-4">
                <p>{rules.editability}</p>
                <p className="mt-1">
                  Source file:{' '}
                  <span className="font-mono">
                    backend/app/libs/metro2_engine.py
                  </span>
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function RuleSection({
  title,
  description,
  pairs,
  children,
}: {
  title: string;
  description: string;
  pairs?: [string, string][];
  children?: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <p className="text-xs text-muted-foreground mb-3">{description}</p>
      {pairs && (
        <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
          {pairs.map(([k, v]) => (
            <div key={k} className="flex justify-between border-b border-border py-1">
              <dt className="text-sm text-muted-foreground capitalize">{k}</dt>
              <dd className="text-sm font-mono text-foreground">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {children}
    </div>
  );
}

function RulePillList({
  label,
  color,
  values,
}: {
  label: string;
  color: 'gray' | 'amber' | 'green' | 'blue';
  values: string[];
}) {
  const colorClass = {
    gray: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
    amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
    green: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    blue: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  }[color];
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground mb-1">{label}</div>
      <div className="flex flex-wrap gap-1">
        {values.length === 0 ? (
          <span className="text-xs text-muted-foreground italic">(none)</span>
        ) : (
          values.map(v => (
            <span
              key={v}
              className={`px-2 py-0.5 rounded text-xs ${colorClass}`}
            >
              {v}
            </span>
          ))
        )}
      </div>
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
