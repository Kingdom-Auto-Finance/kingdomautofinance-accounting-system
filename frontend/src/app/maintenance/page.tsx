'use client';

import { useState, useEffect } from 'react';
import Layout from '@/components/Layout';
import { amortizationAPI, jobsAPI } from '@/lib/api';

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

export default function MaintenancePage() {
  const [importJob, setImportJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Poll job status
  useEffect(() => {
    if (!importJob || (importJob.status !== 'queued' && importJob.status !== 'running')) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const status = await jobsAPI.getStatus(importJob.id);
        setImportJob(status);

        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(interval);
        }
      } catch (err) {
        console.error('Error polling job:', err);
        clearInterval(interval);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [importJob]);

  const handleImportSchedules = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await amortizationAPI.import();
      setImportJob({
        id: response.job_id,
        job_type: 'import_amortization',
        status: 'queued',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start import');
    } finally {
      setLoading(false);
    }
  };

  const renderJobStatus = () => {
    if (!importJob) return null;

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
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Import Job Status</h3>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700">Status:</span>
            <span
              className={`px-3 py-1 rounded-full text-sm font-medium ${statusColors[importJob.status]}`}
            >
              {statusIcons[importJob.status]} {importJob.status.toUpperCase()}
            </span>
          </div>

          {importJob.progress && importJob.status === 'running' && (
            <>
              <div>
                <div className="flex justify-between text-sm text-gray-700 mb-2">
                  <span>{importJob.progress.message}</span>
                  <span>{importJob.progress.percent || 0}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3">
                  <div
                    className="bg-blue-600 h-3 rounded-full transition-all duration-300"
                    style={{ width: `${importJob.progress.percent || 0}%` }}
                  />
                </div>
              </div>
            </>
          )}

          {importJob.status === 'completed' && importJob.result && (
            <div className="p-4 bg-green-50 rounded-lg">
              <p className="text-sm text-green-800">{importJob.result.message}</p>
            </div>
          )}

          {importJob.status === 'failed' && importJob.error && (
            <div className="p-4 bg-red-50 rounded-lg">
              <p className="text-sm text-red-800 font-mono whitespace-pre-wrap">
                {importJob.error}
              </p>
            </div>
          )}

          <p className="text-xs text-gray-500">Job ID: {importJob.id}</p>
        </div>
      </div>
    );
  };

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold text-gray-900">System Maintenance</h1>
          <p className="mt-2 text-sm text-gray-600">
            Import amortization schedules and run system checks
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        {/* Import Amortization Schedules */}
        <div className="bg-white p-6 rounded-lg shadow">
          <div className="flex items-start justify-between mb-4">
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <span>📥</span>
                Import Amortization Schedules
              </h3>
              <p className="mt-2 text-sm text-gray-600">
                Scan Google Drive folder and import loan amortization schedules into database tables.
              </p>
              <ul className="mt-3 text-sm text-gray-600 space-y-1 list-disc list-inside">
                <li>Creates <code className="bg-gray-100 px-1 py-0.5 rounded">schedule_&#123;loan_id&#125;</code> tables</li>
                <li>Imports schedule data from Google Sheets</li>
                <li>Skips tables that already have data</li>
              </ul>
            </div>
          </div>

          <button
            onClick={handleImportSchedules}
            disabled={loading || importJob?.status === 'running'}
            className="w-full px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
          >
            {importJob?.status === 'running' ? 'Importing...' : 'Import Schedules from Google Drive'}
          </button>
        </div>

        {/* Job Status */}
        {renderJobStatus()}

        {/* Info Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
            <h3 className="text-sm font-semibold text-yellow-900 mb-2">⚠️ Important Notes</h3>
            <ul className="text-sm text-yellow-800 space-y-2 list-disc list-inside">
              <li>Import operation can take several minutes</li>
              <li>Only run when you have new loan schedules</li>
              <li>Existing schedules won't be overwritten</li>
            </ul>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
            <h3 className="text-sm font-semibold text-blue-900 mb-2">💡 How it works</h3>
            <ol className="text-sm text-blue-800 space-y-2 list-decimal list-inside">
              <li>Scans your configured Google Drive folder</li>
              <li>Identifies loan spreadsheets by naming pattern</li>
              <li>Creates database tables for each loan</li>
              <li>Imports amortization data into tables</li>
            </ol>
          </div>
        </div>

        {/* Future Features Placeholder */}
        <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
          <h3 className="text-lg font-semibold text-gray-600 mb-2">🚧 Coming Soon</h3>
          <p className="text-sm text-gray-500">
            Additional maintenance features like integrity checks, database backups, and data validation will be added in Phase 3.
          </p>
        </div>
      </div>
    </Layout>
  );
}
