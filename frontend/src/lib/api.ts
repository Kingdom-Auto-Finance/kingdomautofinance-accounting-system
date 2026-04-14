/**
 * API client for FastAPI backend
 */

// Use same origin for API requests (Next.js will proxy to FastAPI backend)
const API_URL = typeof window !== 'undefined' ? window.location.origin : '';
const API_V1 = `${API_URL}/api/v1`;

console.log('✓ API configured:', API_URL);

interface FetchOptions extends RequestInit {
  body?: any;
}

async function fetchAPI<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { body, ...fetchOptions } = options;

  const config: RequestInit = {
    ...fetchOptions,
    headers: {
      'Content-Type': 'application/json',
      ...fetchOptions.headers,
    },
  };

  if (body) {
    config.body = JSON.stringify(body);
  }

  const url = `${API_V1}${endpoint}`;
  console.log('🔄 API Request:', options.method || 'GET', url);

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `HTTP ${response.status}: ${response.statusText}`);
  }

  // Check if response is JSON
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }

  // Return text for CSV responses
  return response.text() as any;
}

/// Payment API
export const paymentsAPI = {
  fetch: (mode: string = 'all', days?: number, startDate?: string, endDate?: string) =>
    fetchAPI<{ job_id: string; message: string }>('/payments/fetch', {
      method: 'POST',
      body: { mode, days, start_date: startDate, end_date: endDate },
    }),

  process: () =>
    fetchAPI<{ job_id: string; message: string }>('/payments/process', {
      method: 'POST',
    }),

  getLog: (params?: { limit?: number; offset?: number; loan_id?: string; processed?: boolean }) =>
    fetchAPI<{ data: any[]; count: number }>(
      `/payments/log?${new URLSearchParams(params as any).toString()}`
    ),
};

// Reports API
export const reportsAPI = {
  summary: (startDate: string, endDate: string) =>
    fetchAPI<string>('/reports/summary', {
      method: 'POST',
      body: { start_date: startDate, end_date: endDate },
    }),

  dayBreakdown: (startDate: string, endDate: string) =>
    fetchAPI<string>('/reports/day-breakdown', {
      method: 'POST',
      body: { start_date: startDate, end_date: endDate },
    }),

  loanBreakdown: (startDate: string, endDate: string) =>
    fetchAPI<string>('/reports/loan-breakdown', {
      method: 'POST',
      body: { start_date: startDate, end_date: endDate },
    }),

  fullBreakdown: (startDate: string, endDate: string) =>
    fetchAPI<string>('/reports/full-breakdown', {
      method: 'POST',
      body: { start_date: startDate, end_date: endDate },
    }),
};

// Amortization API
export const amortizationAPI = {
  import: () =>
    fetchAPI<{ job_id: string; message: string }>('/amortization/import', {
      method: 'POST',
    }),

  getLoans: () => fetchAPI<{ data: any[]; count: number }>('/amortization/loans'),

  getSchedule: (loanId: string, limit: number = 1000) =>
    fetchAPI<{ loan_id: string; data: any[]; count: number }>(
      `/amortization/schedule/${loanId}?limit=${limit}`
    ),
};

// Jobs API
export const jobsAPI = {
  getStatus: (jobId: string) => fetchAPI<any>(`/jobs/${jobId}`),

  list: (params?: { limit?: number; status?: string }) =>
    fetchAPI<{ data: any[]; count: number }>(
      `/jobs/?${new URLSearchParams(params as any).toString()}`
    ),
};

// Audit API
export interface DiscrepancySummary {
  total_discrepancies: number;
  total_affected_loans: number;
}

export interface MonthlyDiscrepanciesResponse {
  year: number;
  month: number;
  discrepancy_dates: string[];
  summary: DiscrepancySummary;
}

export interface DiscrepancyDetail {
  loan_id: string;
  payment_log_id: string;
  payment_date: string;
  payment_log_amount: number;
  schedule_principal: number;
  schedule_interest: number;
  schedule_late_fee: number;
  schedule_total: number;
  difference: number;
}

export interface DateDiscrepanciesResponse {
  date: string;
  discrepancies: DiscrepancyDetail[];
}

export const auditAPI = {
  monthlyDiscrepancies: (year: number, month: number) =>
    fetchAPI<MonthlyDiscrepanciesResponse>('/audit/monthly-discrepancies', {
      method: 'POST',
      body: { year, month },
    }),

  dateDiscrepancies: (date: string) =>
    fetchAPI<DateDiscrepanciesResponse>('/audit/date-discrepancies', {
      method: 'POST',
      body: { date },
    }),
};

// Settings API
export const settingsAPI = {
  getAll: (category?: string) =>
    fetchAPI<{ data: any[]; count: number }>(
      `/settings${category ? `?category=${category}` : ''}`
    ),

  get: (key: string) =>
    fetchAPI<{ key: string; value: string; description: string; category: string }>(
      `/settings/${key}`
    ),

  update: (key: string, value: string, type?: 'sheet' | 'folder') =>
    fetchAPI<{ key: string; value: string; message: string }>(
      `/settings/${key}`,
      {
        method: 'PUT',
        body: { value, type },
      }
    ),

  clearCache: () =>
    fetchAPI<{ message: string }>('/settings/cache/clear', {
      method: 'POST',
    }),
};

// ─── Credit Reports API ──────────────────────────────────────────────────
export interface RunSummary {
  id: string;
  cycle_month: string;
  status: 'draft' | 'final' | 'archived';
  as_of_date_str: string;
  ready_count: number;
  review_count: number;
  excluded_count: number;
  carried_over_count: number;
  skipped_count?: number;
  created_at?: string;
  finalized_at?: string;
  note?: string;
}

export interface Validation {
  id?: number;
  severity: 'FATAL' | 'WARNING' | 'INFO';
  code: string;
  message: string;
  affected_count?: number;
  affected_deal_ids?: string[] | null;
}

export interface RunDetail {
  run: RunSummary;
  validations: Validation[];
}

export interface RunItem {
  id: string;
  run_id: string;
  deal_id: string;
  bucket: 'ready' | 'review' | 'excluded' | 'carried' | 'skipped';
  reason?: string;
  source_row: Record<string, any>;
  metro2_row?: Record<string, any>;
  review_decision?: 'approve' | 'exclude' | 'defer' | 'skip';
  review_metro2_status_code?: string;
  review_fcra_dofi?: string;
  review_note?: string;
  business_flag_source?: 'auto' | 'manual_on' | 'manual_off';
  was_in_prior_cycle: boolean;
  missing_from_upload: boolean;
}

export interface CreateDraftResponse {
  run_id: string;
  ready_count: number;
  review_count: number;
  excluded_count: number;
  carried_over_count: number;
}

export interface ListItemsResponse {
  data: RunItem[];
  page: number;
  page_size: number;
  total: number;
}

export const creditReportAPI = {
  /** Upload two MongoDB CSVs and create a new draft run. */
  createDraft: async (
    dealFile: File,
    addressFile: File,
    cycleMonth?: string
  ): Promise<CreateDraftResponse> => {
    const form = new FormData();
    form.append('deal_csv', dealFile);
    form.append('address_csv', addressFile);
    if (cycleMonth) form.append('cycle_month', cycleMonth);

    const response = await fetch(`${API_V1}/credit-reports/runs/draft`, {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    return response.json();
  },

  listRuns: (limit = 20) =>
    fetchAPI<{ data: RunSummary[]; count: number }>(
      `/credit-reports/runs?limit=${limit}`
    ),

  getRun: (runId: string) =>
    fetchAPI<RunDetail>(`/credit-reports/runs/${runId}`),

  listItems: (
    runId: string,
    params: {
      bucket?: string;
      q?: string;
      page?: number;
      page_size?: number;
      order_by?: string;
      order_dir?: 'asc' | 'desc';
      deal_ids?: string[];
    } = {}
  ) => {
    const qs = new URLSearchParams();
    if (params.bucket) qs.set('bucket', params.bucket);
    if (params.q) qs.set('q', params.q);
    if (params.page) qs.set('page', String(params.page));
    if (params.page_size) qs.set('page_size', String(params.page_size));
    if (params.order_by) qs.set('order_by', params.order_by);
    if (params.order_dir) qs.set('order_dir', params.order_dir);
    if (params.deal_ids && params.deal_ids.length) {
      qs.set('deal_ids', params.deal_ids.join(','));
    }
    return fetchAPI<ListItemsResponse>(
      `/credit-reports/runs/${runId}/items?${qs.toString()}`
    );
  },

  downloadCsv: (
    runId: string,
    bucket: 'ready' | 'review' | 'excluded' | 'carried' | 'skipped'
  ) => fetchAPI<string>(`/credit-reports/runs/${runId}/download/${bucket}`),

  downloadReport: (runId: string) =>
    fetchAPI<string>(`/credit-reports/runs/${runId}/download-report`),

  setBusinessFlag: (
    runId: string,
    dealId: string,
    body: { is_business: boolean; note?: string }
  ) =>
    fetchAPI<RunItem>(`/credit-reports/runs/${runId}/items/${dealId}/business-flag`, {
      method: 'POST',
      body,
    }),

  setReviewDecision: (
    runId: string,
    dealId: string,
    body: {
      decision: 'approve' | 'exclude' | 'defer' | 'skip';
      metro2_status_code?: string;
      fcra_dofi?: string;
      note?: string;
    }
  ) =>
    fetchAPI<RunItem>(`/credit-reports/runs/${runId}/items/${dealId}/review-decision`, {
      method: 'POST',
      body,
    }),

  finalize: (runId: string, body: { force?: boolean; note?: string }) =>
    fetchAPI<RunDetail>(`/credit-reports/runs/${runId}/finalize`, {
      method: 'POST',
      body,
    }),

  deleteDraft: (runId: string) =>
    fetchAPI<{ message: string }>(`/credit-reports/runs/${runId}`, { method: 'DELETE' }),

  getRules: () =>
    fetchAPI<{
      experian_config: Record<string, string>;
      status_buckets: Record<string, string[]>;
      business_pattern: string;
      frequency_map: Record<string, { metro2_code: string }>;
      address_field_candidates: Record<string, string[]>;
      metro2_columns: string[];
      editability: string;
    }>('/credit-reports/rules'),
};

// ─── Metro 2 native platform API (Switch Labs parity) ────────────────────────
export interface Metro2Field {
  name: string;
  label: string;
  position: number;
  length: number;
  type: string;
  importance: 'required' | 'recommended' | 'optional';
  description: string;
  format: string;
  sample: string;
  db_column: string | null;
  allowed_values: string[] | null;
}

export interface Metro2Schema {
  fields: Metro2Field[];
  counts: { total: number; required: number; recommended: number; optional: number };
  config: Record<string, any>;
  status_rules: Record<string, string[]>;
}

export interface Metro2Record {
  id: string;
  subscriber_code: string;
  consumer_account_number: string;
  surname?: string;
  first_name?: string;
  account_status?: string;
  current_balance?: number;
  amount_past_due?: number;
  origin: 'cycle' | 'manual';
  is_active: boolean;
  last_validated_at?: string;
  last_validated_status?: 'clean' | 'warning' | 'fatal';
  last_validation_issues?: any[];
  [key: string]: any;
}

export interface MappingSuggestion {
  source_column: string;
  suggested_field: string | null;
  confidence: number;
  sample_values: string[];
  importance: 'required' | 'recommended' | 'optional' | null;
}

export interface MappingCheck {
  total_required: number;
  mapped_required: number;
  missing_required: string[];
  total_recommended: number;
  mapped_recommended: number;
  missing_recommended: string[];
  is_valid: boolean;
}

export interface ValidationReportDTO {
  status: 'clean' | 'warning' | 'fatal';
  fatal_count: number;
  warning_count: number;
  findings: {
    severity: string;
    code: string;
    field: string | null;
    message: string;
    row_index: number | null;
    account_number: string | null;
  }[];
}

export interface Metro2FileRow {
  id: string;
  filename: string;
  as_of_date: string;
  record_count: number;
  total_current_balance: number;
  total_past_due: number;
  sha256: string;
  size_bytes: number;
  generated_at: string;
}

export const metro2API = {
  // Schema / Account
  getSchema: () => fetchAPI<Metro2Schema>('/credit-reports/metro2/schema'),
  getAccount: () =>
    fetchAPI<Record<string, any>>('/credit-reports/metro2/account'),

  // File Upload
  uploadFile: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_V1}/credit-reports/metro2/upload`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{
      batch_id: string;
      filename: string;
      row_count: number;
      headers: string[];
      suggestions: MappingSuggestion[];
      sample_rows: Record<string, string>[];
    }>;
  },
  validateMapping: (batch_id: string, mapping: Record<string, string>) =>
    fetchAPI<{ mapping: MappingCheck; validation: ValidationReportDTO }>(
      '/credit-reports/metro2/upload/validate',
      { method: 'POST', body: { batch_id, mapping } },
    ),
  acceptUpload: (batch_id: string, mapping: Record<string, string>, force = false) =>
    fetchAPI<{
      batch_id: string;
      inserted: number;
      skipped: number;
      skip_reasons: { row_index: number; account_number?: string; error: string }[];
      validation: ValidationReportDTO;
    }>('/credit-reports/metro2/upload/accept', {
      method: 'POST',
      body: { batch_id, mapping, force },
    }),

  // Mapping templates
  listMappingTemplates: () =>
    fetchAPI<{ data: any[] }>('/credit-reports/metro2/mapping-templates'),
  saveMappingTemplate: (body: {
    name: string;
    mapping: Record<string, string>;
    description?: string;
    is_default?: boolean;
  }) =>
    fetchAPI<any>('/credit-reports/metro2/mapping-templates', {
      method: 'POST',
      body,
    }),
  deleteMappingTemplate: (id: string) =>
    fetchAPI<any>(`/credit-reports/metro2/mapping-templates/${id}`, {
      method: 'DELETE',
    }),

  // Records
  listRecords: (params: {
    origin?: string;
    status?: string;
    validation_status?: string;
    q?: string;
    only_active?: boolean;
    page?: number;
    page_size?: number;
  } = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.append(k, String(v));
    });
    return fetchAPI<{
      data: Metro2Record[];
      page: number;
      page_size: number;
      total: number;
    }>(`/credit-reports/metro2/records?${qs.toString()}`);
  },
  getRecord: (id: string) =>
    fetchAPI<Metro2Record>(`/credit-reports/metro2/records/${id}`),
  getRecordHistory: (id: string) =>
    fetchAPI<{ data: any[] }>(`/credit-reports/metro2/records/${id}/history`),
  createRecord: (fields: Record<string, any>) =>
    fetchAPI<Metro2Record>('/credit-reports/metro2/records', {
      method: 'POST',
      body: { fields },
    }),
  updateRecord: (id: string, fields: Record<string, any>, note?: string) =>
    fetchAPI<Metro2Record>(`/credit-reports/metro2/records/${id}`, {
      method: 'PATCH',
      body: { fields, note },
    }),
  deactivateRecord: (id: string) =>
    fetchAPI<Metro2Record>(
      `/credit-reports/metro2/records/${id}/deactivate`,
      { method: 'POST' },
    ),
  reactivateRecord: (id: string) =>
    fetchAPI<Metro2Record>(
      `/credit-reports/metro2/records/${id}/reactivate`,
      { method: 'POST' },
    ),
  revalidateRecord: (id: string) =>
    fetchAPI<Metro2Record>(
      `/credit-reports/metro2/records/${id}/revalidate`,
      { method: 'POST' },
    ),

  // Analytics
  getAnalytics: () =>
    fetchAPI<{
      total_records: number;
      total_balance: number;
      total_past_due: number;
      status_distribution: Record<string, number>;
      origin_distribution: Record<string, number>;
      validation_distribution: Record<string, number>;
      recent_files: Metro2FileRow[];
    }>('/credit-reports/metro2/analytics'),

  // Files
  generateFile: (body: {
    as_of_date?: string;
    record_ids?: string[];
    force?: boolean;
    enforce_minimum?: boolean;
  } = {}) =>
    fetchAPI<{
      file_id: string;
      filename: string;
      storage_path: string;
      sha256: string;
      size_bytes: number;
      as_of_date: string;
      record_count: number;
      total_current_balance: number;
      total_past_due: number;
      status_11_count: number;
      validation: ValidationReportDTO;
    }>('/credit-reports/metro2/files/generate', { method: 'POST', body }),
  listFiles: (limit = 50) =>
    fetchAPI<{ data: Metro2FileRow[] }>(
      `/credit-reports/metro2/files?limit=${limit}`,
    ),
  getFile: (id: string) =>
    fetchAPI<any>(`/credit-reports/metro2/files/${id}`),
  downloadFileUrl: (id: string) =>
    `${API_V1}/credit-reports/metro2/files/${id}/download`,

  // Transmissions
  listTransmissions: () =>
    fetchAPI<{ data: any[] }>('/credit-reports/metro2/transmissions'),
  logTransmission: (body: {
    file_id: string;
    transmitted_at: string;
    confirmation_ref?: string;
    notes?: string;
  }) =>
    fetchAPI<any>('/credit-reports/metro2/transmissions', {
      method: 'POST',
      body,
    }),

  // Responses
  listResponses: () =>
    fetchAPI<{ data: any[] }>('/credit-reports/metro2/responses'),
  uploadResponse: async (file: File, transmission_id?: string) => {
    const form = new FormData();
    form.append('file', file);
    if (transmission_id) form.append('transmission_id', transmission_id);
    const res = await fetch(
      `${API_V1}/credit-reports/metro2/responses/upload`,
      { method: 'POST', body: form },
    );
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // Disputes
  listDisputes: (status?: string) => {
    const qs = status ? `?status=${status}` : '';
    return fetchAPI<{ data: any[] }>(`/credit-reports/metro2/disputes${qs}`);
  },
  createDispute: (body: {
    record_id?: string;
    dispute_code?: string;
    received_at: string;
    notes?: string;
  }) =>
    fetchAPI<any>('/credit-reports/metro2/disputes', {
      method: 'POST',
      body,
    }),
  updateDispute: (id: string, body: Record<string, any>) =>
    fetchAPI<any>(`/credit-reports/metro2/disputes/${id}`, {
      method: 'PATCH',
      body,
    }),

  // Schedules (v1 placeholder)
  getSchedules: () =>
    fetchAPI<{ enabled: boolean; message: string }>(
      '/credit-reports/metro2/schedules',
    ),
};

// Health check
export const healthCheck = () =>
  fetch(`${API_URL}/health`).then(res => res.json());

// Default export for backwards compatibility
export default {
  paymentsAPI,
  reportsAPI,
  amortizationAPI,
  jobsAPI,
  auditAPI,
  settingsAPI,
  creditReportAPI,
  metro2API,
  healthCheck,
};
