'use client';

import { useState } from 'react';
import Layout from '@/components/Layout';
import DateInput from '@/components/DateInput';
import { reportsAPI } from '@/lib/api';
import { downloadCSV, formatDate } from '@/lib/utils';

export default function DashboardPage() {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [reportData, setReportData] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerateReport = async () => {
    if (!startDate || !endDate) {
      setError('Please select both start and end dates');
      return;
    }

    setLoading(true);
    setError(null);
    setReportData(null);

    try {
      const csv = await reportsAPI.summary(startDate, endDate);
      setReportData(csv);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate report');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (reportData) {
      downloadCSV(reportData, `summary_report_${startDate}_${endDate}.csv`);
    }
  };

  const parseCSV = (csv: string) => {
    const lines = csv.trim().split('\n');
    if (lines.length < 2) return null;

    const headers = lines[0].split(',');
    const values = lines[1].split(',');

    return headers.reduce((acc, header, index) => {
      acc[header.trim()] = values[index]?.trim() || '0';
      return acc;
    }, {} as Record<string, string>);
  };

  const summary = reportData ? parseCSV(reportData) : null;

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold text-foreground">Dashboard</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            View summary reports and system overview
          </p>
        </div>

        {/* Date Range Selector */}
        <div className="bg-card p-6 rounded-lg shadow border border-border">
          <h2 className="text-lg font-semibold text-card-foreground mb-4">
            Generate Summary Report
          </h2>

          <div className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="block text-sm font-medium text-foreground mb-2">
                Start Date
              </label>
              <DateInput
                value={startDate}
                onChange={setStartDate}
                placeholder="mm/dd/yyyy"
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-card text-foreground"
              />
            </div>

            <div className="flex-1">
              <label className="block text-sm font-medium text-foreground mb-2">
                End Date
              </label>
              <DateInput
                value={endDate}
                onChange={setEndDate}
                placeholder="mm/dd/yyyy"
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-card text-foreground"
              />
            </div>

            <button
              onClick={handleGenerateReport}
              disabled={loading}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Generating...' : 'Generate Report'}
            </button>
          </div>

          {error && (
            <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}
        </div>

        {/* Summary Cards */}
        {summary && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-card p-6 rounded-lg shadow border border-border">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Principal</p>
                  <p className="mt-2 text-3xl font-bold text-foreground">
                    ${parseFloat(summary['Total Principal'] || '0').toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="p-3 bg-info-muted rounded-full">
                  <span className="text-2xl">💵</span>
                </div>
              </div>
            </div>

            <div className="bg-card p-6 rounded-lg shadow border border-border">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Interest</p>
                  <p className="mt-2 text-3xl font-bold text-foreground">
                    ${parseFloat(summary['Total Interest'] || '0').toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="p-3 bg-success-muted rounded-full">
                  <span className="text-2xl">📈</span>
                </div>
              </div>
            </div>

            <div className="bg-card p-6 rounded-lg shadow border border-border">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Late Fees</p>
                  <p className="mt-2 text-3xl font-bold text-foreground">
                    ${parseFloat(summary['Total Late Fees'] || '0').toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="p-3 bg-warning-muted rounded-full">
                  <span className="text-2xl">⚠️</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Download Button */}
        {reportData && (
          <div className="bg-card p-6 rounded-lg shadow border border-border">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-foreground">Report Ready</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Summary report for {formatDate(startDate)} to {formatDate(endDate)}
                </p>
              </div>
              <button
                onClick={handleDownload}
                className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors flex items-center gap-2"
              >
                <span>⬇️</span>
                Download CSV
              </button>
            </div>
          </div>
        )}

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-accent hover:bg-accent/90 p-6 rounded-lg shadow border border-border transition-colors">
            <h3 className="text-lg font-semibold text-foreground mb-2">
              💰 Process Payments
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              Process unprocessed payments from your payment log
            </p>
            <a
              href="/payments"
              className="inline-block px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
            >
              Go to Payments →
            </a>
          </div>

          <div className="bg-accent hover:bg-accent/90 p-6 rounded-lg shadow border border-border transition-colors">
            <h3 className="text-lg font-semibold text-foreground mb-2">
              ⚙️ System Maintenance
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              Import schedules, run integrity checks
            </p>
            <a
              href="/maintenance"
              className="inline-block px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm font-medium"
            >
              Go to Maintenance →
            </a>
          </div>
        </div>
      </div>
    </Layout>
  );
}
