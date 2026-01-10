'use client';

import { useState } from 'react';
import Layout from '@/components/Layout';
import DateInput from '@/components/DateInput';
import { reportsAPI } from '@/lib/api';
import { downloadCSV, formatDate } from '@/lib/utils';

type ReportType = 'summary' | 'day' | 'loan' | 'full';

export default function ReportsPage() {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reportType, setReportType] = useState<ReportType>('summary');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const reportTypes = [
    {
      value: 'summary',
      label: 'Summary Report',
      description: 'Total principal, interest, and fees',
      icon: '📊',
    },
    {
      value: 'day',
      label: 'Day Breakdown',
      description: 'Daily totals by payment date',
      icon: '📅',
    },
    {
      value: 'loan',
      label: 'Loan Breakdown',
      description: 'Totals by loan ID',
      icon: '🏦',
    },
    {
      value: 'full',
      label: 'Full Breakdown',
      description: 'Detailed breakdown by loan and date',
      icon: '📋',
    },
  ];

  const handleGenerateAndDownload = async () => {
    if (!startDate || !endDate) {
      setError('Please select both start and end dates');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      let csv: string;

      switch (reportType) {
        case 'summary':
          csv = await reportsAPI.summary(startDate, endDate);
          break;
        case 'day':
          csv = await reportsAPI.dayBreakdown(startDate, endDate);
          break;
        case 'loan':
          csv = await reportsAPI.loanBreakdown(startDate, endDate);
          break;
        case 'full':
          csv = await reportsAPI.fullBreakdown(startDate, endDate);
          break;
      }

      // Auto-download
      const filename = `${reportType}_report_${startDate}_${endDate}.csv`;
      downloadCSV(csv, filename);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate report');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold text-foreground">Reports</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Generate and download detailed payment reports
          </p>
        </div>

        {/* Report Configuration */}
        <div className="bg-card p-6 rounded-lg shadow border border-border">
          <h2 className="text-lg font-semibold text-foreground mb-4">
            Configure Report
          </h2>

          {/* Date Range */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
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

            <div>
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
          </div>

          {/* Report Type Selection */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-3">
              Report Type
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {reportTypes.map((type) => (
                <button
                  key={type.value}
                  onClick={() => setReportType(type.value as ReportType)}
                  className={`p-4 border-2 rounded-lg text-left transition-all ${
                    reportType === type.value
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-950'
                      : 'border-border hover:border-foreground/30'
                  }`}
                >
                  <div className="flex items-start">
                    <span className="text-2xl mr-3">{type.icon}</span>
                    <div>
                      <h3 className="font-semibold text-foreground">{type.label}</h3>
                      <p className="text-sm text-muted-foreground mt-1">{type.description}</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Generate Button */}
          <div className="mt-6">
            <button
              onClick={handleGenerateAndDownload}
              disabled={loading || !startDate || !endDate}
              className="w-full px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="animate-spin">⚙️</span>
                  Generating Report...
                </>
              ) : (
                <>
                  <span>⬇️</span>
                  Generate & Download CSV
                </>
              )}
            </button>
          </div>

          {/* Feedback Messages */}
          {error && (
            <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {success && (
            <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <p className="text-sm text-green-800">
                ✅ Report generated and downloaded successfully!
              </p>
            </div>
          )}
        </div>

        {/* Report Descriptions */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="text-sm font-semibold text-blue-900 mb-3">📖 Report Descriptions</h3>
          <dl className="space-y-3">
            <div>
              <dt className="text-sm font-medium text-blue-900">Summary Report</dt>
              <dd className="text-sm text-blue-800 mt-1">
                High-level overview with total principal paid, interest paid, late fees, and payment count for the date range.
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-blue-900">Day Breakdown</dt>
              <dd className="text-sm text-blue-800 mt-1">
                Shows daily totals grouped by payment date. Useful for tracking daily cash flow.
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-blue-900">Loan Breakdown</dt>
              <dd className="text-sm text-blue-800 mt-1">
                Groups payments by loan ID. Useful for seeing which loans are performing.
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-blue-900">Full Breakdown</dt>
              <dd className="text-sm text-blue-800 mt-1">
                Most detailed report showing every payment with loan ID, date, and all amounts. Best for detailed analysis.
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </Layout>
  );
}
