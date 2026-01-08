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

// Health check
export const healthCheck = () =>
  fetch(`${API_URL}/health`).then(res => res.json());

// Default export for backwards compatibility
export default {
  paymentsAPI,
  reportsAPI,
  amortizationAPI,
  jobsAPI,
  healthCheck,
};
