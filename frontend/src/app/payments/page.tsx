'use client';

import { useState, useEffect } from 'react';
import Layout from '@/components/Layout';
import { paymentsAPI, jobsAPI } from '@/lib/api';

type JobStatus = {
  id: string;
  job_type: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress?: {
    current: number;
    total: number;
    message: string;
    percent?: number;
  };
  error?: string;
  result?: any;
};

export default function PaymentsPage() {
  const [fetchJob, setFetchJob] = useState<JobStatus | null>(null);
  const [processJob, setProcessJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Poll job status
  useEffect(() => {
    const pollJob = async (jobId: string, setJob: (job: JobStatus) => void) => {
      try {
        const status = await jobsAPI.getStatus(jobId);
        setJob(status);

        // Stop polling if job is done
        if (status.status === 'completed' || status.status === 'failed') {
          return true;
        }
        return false;
      } catch (err) {
        console.error('Error polling job:', err);
        return true; // Stop polling on error
      }
    };

    const intervals: NodeJS.Timeout[] = [];

    if (fetchJob && (fetchJob.status === 'queued' || fetchJob.status === 'running')) {
      const interval = setInterval(async () => {
        const done = await pollJob(fetchJob.id, setFetchJob);
        if (done) clearInterval(interval);
      }, 2000);
      intervals.push(interval);
    }

    if (processJob && (processJob.status === 'queued' || processJob.status === 'running')) {
      const interval = setInterval(async () => {
        const done = await pollJob(processJob.id, setProcessJob);
        if (done) clearInterval(interval);
      }, 2000);
      intervals.push(interval);
    }

    return () => intervals.forEach(clearInterval);
  }, [fetchJob, processJob]);

  const handleFetchPayments = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await paymentsAPI.fetch('all');
      setFetchJob({
        id: response.job_id,
        job_type: 'fetch_payments',
        status: 'queued',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start fetch');
    } finally {
      setLoading(false);
    }
  };

  const handleProcessPayments = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await paymentsAPI.process();
      setProcessJob({
        id: response.job_id,
        job_type: 'process_payments',
        status: 'queued',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start processing');
    } finally {
      setLoading(false);
    }
  };

  const renderJobStatus = (job: JobStatus | null, title: string) => {
    if (!job) return null;

    const statusColors = {
      queued: 'bg-gray-100 text-gray-800',
      running: 'bg-blue-100 text-blue-800',
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
    };

    const statusIcons = {
      queued: '⏳',
      running: '⚙️',
      completed: '✅',
      failed: '❌',
    };

    return (
      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">{title}</h3>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700">Status:</span>
            <span
              className={`px-3 py-1 rounded-full text-sm font-medium ${statusColors[job.status]}`}
            >
              {statusIcons[job.status]} {job.status.toUpperCase()}
            </span>
          </div>

          {job.progress && job.status === 'running' && (
            <>
              <div>
                <div className="flex justify-between text-sm text-gray-700 mb-2">
                  <span>{job.progress.message}</span>
                  <span>{job.progress.percent || 0}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3">
                  <div
                    className="bg-blue-600 h-3 rounded-full transition-all duration-300"
                    style={{ width: `${job.progress.percent || 0}%` }}
                  />
                </div>
              </div>
            </>
          )}

          {job.status === 'completed' && job.result && (
            <div className="p-4 bg-green-50 rounded-lg">
              <p className="text-sm text-green-800">{job.result.message}</p>
            </div>
          )}

          {job.status === 'failed' && job.error && (
            <div className="p-4 bg-red-50 rounded-lg">
              <p className="text-sm text-red-800 font-mono">{job.error}</p>
            </div>
          )}

          <p className="text-xs text-gray-500">Job ID: {job.id}</p>
        </div>
      </div>
    );
  };

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Payment Management</h1>
          <p className="mt-2 text-sm text-gray-600">
            Fetch payments from Google Sheets and process them
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white p-6 rounded-lg shadow">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  1️⃣ Fetch Payments
                </h3>
                <p className="mt-1 text-sm text-gray-600">
                  Import new payments from Google Sheets
                </p>
              </div>
            </div>
            <button
              onClick={handleFetchPayments}
              disabled={loading || (fetchJob?.status === 'running')}
              className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
            >
              {fetchJob?.status === 'running' ? 'Fetching...' : 'Fetch Payments'}
            </button>
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  2️⃣ Process Payments
                </h3>
                <p className="mt-1 text-sm text-gray-600">
                  Allocate payments to amortization schedules
                </p>
              </div>
            </div>
            <button
              onClick={handleProcessPayments}
              disabled={loading || (processJob?.status === 'running')}
              className="w-full px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
            >
              {processJob?.status === 'running' ? 'Processing...' : 'Process Payments'}
            </button>
          </div>
        </div>

        {/* Job Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {renderJobStatus(fetchJob, 'Fetch Job Status')}
          {renderJobStatus(processJob, 'Process Job Status')}
        </div>

        {/* Info Card */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="text-sm font-semibold text-blue-900 mb-2">💡 How it works</h3>
          <ol className="text-sm text-blue-800 space-y-2 list-decimal list-inside">
            <li>
              <strong>Fetch Payments:</strong> Retrieves new payments from your Google Sheets source
            </li>
            <li>
              <strong>Process Payments:</strong> Allocates payments to loan schedules, calculating principal, interest, and late fees
            </li>
            <li>
              Both operations run in the background and you can track their progress in real-time
            </li>
          </ol>
        </div>
      </div>
    </Layout>
  );
}
