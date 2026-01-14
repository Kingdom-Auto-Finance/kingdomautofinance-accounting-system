'use client';

import { useState } from 'react';
import Layout from '@/components/Layout';
import DateInput from '@/components/DateInput';
import { reportsAPI } from '@/lib/api';
import { downloadCSV, formatDate } from '@/lib/utils';

type ReportType = 'summary' | 'day' | 'loan' | 'full';

interface ParsedSummary {
  total_principal: string;
  total_interest: string;
  total_fees: string;
}

interface ParsedRow {
  [key: string]: string;
}

export default function ReportsPage() {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reportType, setReportType] = useState<ReportType>('summary');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportData, setReportData] = useState<string | null>(null);

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

  const handleGenerateReport = async () => {
    if (!startDate || !endDate) {
      setError('Please select both start and end dates');
      return;
    }

    setLoading(true);
    setError(null);
    setReportData(null);

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

      setReportData(csv);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate report');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (reportData) {
      const filename = `${reportType}_report_${startDate}_${endDate}.csv`;
      downloadCSV(reportData, filename);
    }
  };

  // Parse CSV into summary object (for summary report)
  const parseSummaryCSV = (csv: string): ParsedSummary | null => {
    const lines = csv.trim().split('\n');
    if (lines.length < 2) return null;

    const headers = lines[0].split(',');
    const values = lines[1].split(',');

    const result: Record<string, string> = {};
    headers.forEach((header, index) => {
      result[header.trim()] = values[index]?.trim() || '0';
    });

    return {
      total_principal: result['total_principal'] || '0',
      total_interest: result['total_interest'] || '0',
      total_fees: result['total_fees'] || '0',
    };
  };

  // Parse CSV into array of rows (for breakdown reports)
  const parseBreakdownCSV = (csv: string): { headers: string[]; rows: ParsedRow[] } | null => {
    const lines = csv.trim().split('\n');
    if (lines.length < 1) return null;

    const headers = lines[0].split(',').map(h => h.trim());
    const rows: ParsedRow[] = [];

    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',');
      const row: ParsedRow = {};
      headers.forEach((header, index) => {
        row[header] = values[index]?.trim() || '';
      });
      rows.push(row);
    }

    return { headers, rows };
  };

  const summary = reportData && reportType === 'summary' ? parseSummaryCSV(reportData) : null;
  const breakdown = reportData && reportType !== 'summary' ? parseBreakdownCSV(reportData) : null;

  // Calculate totals from breakdown rows
  const calculateBreakdownTotals = (headers: string[], rows: ParsedRow[]) => {
    const totals: Record<string, number> = {};

    headers.forEach(header => {
      const lowerHeader = header.toLowerCase();
      // Only sum numeric columns (amounts, principal, interest, fees)
      if (lowerHeader.includes('amount') || lowerHeader.includes('principal') || lowerHeader.includes('interest') || lowerHeader.includes('fee')) {
        totals[header] = rows.reduce((sum, row) => {
          const val = parseFloat(row[header] || '0');
          return sum + (isNaN(val) ? 0 : val);
        }, 0);
      }
    });

    return totals;
  };

  const breakdownTotals = breakdown ? calculateBreakdownTotals(breakdown.headers, breakdown.rows) : null;

  // Format column header for display
  const formatHeader = (header: string): string => {
    return header
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  };

  // Format cell value based on column type
  const formatCellValue = (header: string, value: string): string => {
    const lowerHeader = header.toLowerCase();
    if (lowerHeader.includes('amount') || lowerHeader.includes('principal') || lowerHeader.includes('interest') || lowerHeader.includes('fee')) {
      const num = parseFloat(value);
      if (!isNaN(num)) {
        return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      }
    }
    return value;
  };

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold text-foreground">Reports</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Generate and view detailed payment reports
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
                  onClick={() => {
                    setReportType(type.value as ReportType);
                    setReportData(null); // Clear previous report when changing type
                  }}
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
              onClick={handleGenerateReport}
              disabled={loading || !startDate || !endDate}
              className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="animate-spin">⚙️</span>
                  Generating Report...
                </>
              ) : (
                <>
                  <span>📊</span>
                  Generate Report
                </>
              )}
            </button>
          </div>

          {/* Error Message */}
          {error && (
            <div className="mt-4 p-4 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
            </div>
          )}
        </div>

        {/* Summary Report Display */}
        {summary && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-card p-6 rounded-lg shadow border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Principal</p>
                    <p className="mt-2 text-3xl font-bold text-foreground">
                      ${parseFloat(summary.total_principal || '0').toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="p-3 bg-blue-100 dark:bg-blue-900 rounded-full">
                    <span className="text-2xl">💵</span>
                  </div>
                </div>
              </div>

              <div className="bg-card p-6 rounded-lg shadow border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Interest</p>
                    <p className="mt-2 text-3xl font-bold text-foreground">
                      ${parseFloat(summary.total_interest || '0').toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="p-3 bg-green-100 dark:bg-green-900 rounded-full">
                    <span className="text-2xl">📈</span>
                  </div>
                </div>
              </div>

              <div className="bg-card p-6 rounded-lg shadow border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Late Fees</p>
                    <p className="mt-2 text-3xl font-bold text-foreground">
                      ${parseFloat(summary.total_fees || '0').toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="p-3 bg-yellow-100 dark:bg-yellow-900 rounded-full">
                    <span className="text-2xl">⚠️</span>
                  </div>
                </div>
              </div>

              <div className="bg-card p-6 rounded-lg shadow border-2 border-purple-500 dark:border-purple-400">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Received</p>
                    <p className="mt-2 text-3xl font-bold text-purple-600 dark:text-purple-400">
                      ${(
                        parseFloat(summary.total_principal || '0') +
                        parseFloat(summary.total_interest || '0') +
                        parseFloat(summary.total_fees || '0')
                      ).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="p-3 bg-purple-100 dark:bg-purple-900 rounded-full">
                    <span className="text-2xl">💰</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Breakdown Report Display (Table) */}
        {breakdown && breakdown.rows.length > 0 && breakdownTotals && (
          <>
            {/* Summary Cards for Breakdown Reports */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-card p-6 rounded-lg shadow border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Principal</p>
                    <p className="mt-2 text-3xl font-bold text-foreground">
                      ${(breakdownTotals['principal_amount'] || breakdownTotals['total_principal'] || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="p-3 bg-blue-100 dark:bg-blue-900 rounded-full">
                    <span className="text-2xl">💵</span>
                  </div>
                </div>
              </div>

              <div className="bg-card p-6 rounded-lg shadow border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Interest</p>
                    <p className="mt-2 text-3xl font-bold text-foreground">
                      ${(breakdownTotals['interest_amount'] || breakdownTotals['total_interest'] || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="p-3 bg-green-100 dark:bg-green-900 rounded-full">
                    <span className="text-2xl">📈</span>
                  </div>
                </div>
              </div>

              <div className="bg-card p-6 rounded-lg shadow border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Late Fees</p>
                    <p className="mt-2 text-3xl font-bold text-foreground">
                      ${(breakdownTotals['fee_amount'] || breakdownTotals['total_fees'] || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="p-3 bg-yellow-100 dark:bg-yellow-900 rounded-full">
                    <span className="text-2xl">⚠️</span>
                  </div>
                </div>
              </div>

              <div className="bg-card p-6 rounded-lg shadow border-2 border-purple-500 dark:border-purple-400">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Received</p>
                    <p className="mt-2 text-3xl font-bold text-purple-600 dark:text-purple-400">
                      ${(
                        (breakdownTotals['principal_amount'] || breakdownTotals['total_principal'] || 0) +
                        (breakdownTotals['interest_amount'] || breakdownTotals['total_interest'] || 0) +
                        (breakdownTotals['fee_amount'] || breakdownTotals['total_fees'] || 0)
                      ).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div className="p-3 bg-purple-100 dark:bg-purple-900 rounded-full">
                    <span className="text-2xl">💰</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Table */}
            <div className="bg-card rounded-lg shadow border border-border overflow-hidden">
              <div className="p-4 border-b border-border">
                <h3 className="text-lg font-semibold text-foreground">
                  {reportTypes.find(t => t.value === reportType)?.label} Results
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  {breakdown.rows.length} record{breakdown.rows.length !== 1 ? 's' : ''} found for {formatDate(startDate)} to {formatDate(endDate)}
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-muted/50">
                    <tr>
                      {breakdown.headers.map((header) => (
                        <th
                          key={header}
                          className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                        >
                          {formatHeader(header)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {breakdown.rows.map((row, rowIndex) => (
                      <tr key={rowIndex} className="hover:bg-muted/30 transition-colors">
                        {breakdown.headers.map((header) => (
                          <td
                            key={header}
                            className="px-4 py-3 text-sm text-foreground whitespace-nowrap"
                          >
                            {formatCellValue(header, row[header])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-purple-50 dark:bg-purple-950 border-t-2 border-purple-500 dark:border-purple-400">
                    <tr>
                      {breakdown.headers.map((header, index) => (
                        <td
                          key={header}
                          className="px-4 py-3 text-sm font-bold text-purple-700 dark:text-purple-300 whitespace-nowrap"
                        >
                          {index === 0 ? 'TOTALS' : (
                            breakdownTotals[header] !== undefined
                              ? '$' + breakdownTotals[header].toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                              : ''
                          )}
                        </td>
                      ))}
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          </>
        )}

        {/* Empty State for Breakdown */}
        {breakdown && breakdown.rows.length === 0 && (
          <div className="bg-card p-6 rounded-lg shadow border border-border text-center">
            <p className="text-muted-foreground">No data found for the selected date range.</p>
          </div>
        )}

        {/* Download Button */}
        {reportData && (
          <div className="bg-card p-6 rounded-lg shadow border border-border">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-foreground">Download Report</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  {reportTypes.find(t => t.value === reportType)?.label} for {formatDate(startDate)} to {formatDate(endDate)}
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

        {/* Report Descriptions */}
        <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-6">
          <h3 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-3">📖 Report Descriptions</h3>
          <dl className="space-y-3">
            <div>
              <dt className="text-sm font-medium text-blue-900 dark:text-blue-100">Summary Report</dt>
              <dd className="text-sm text-blue-800 dark:text-blue-200 mt-1">
                High-level overview with total principal paid, interest paid, late fees, and payment count for the date range.
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-blue-900 dark:text-blue-100">Day Breakdown</dt>
              <dd className="text-sm text-blue-800 dark:text-blue-200 mt-1">
                Shows daily totals grouped by payment date. Useful for tracking daily cash flow.
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-blue-900 dark:text-blue-100">Loan Breakdown</dt>
              <dd className="text-sm text-blue-800 dark:text-blue-200 mt-1">
                Groups payments by loan ID. Useful for seeing which loans are performing.
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-blue-900 dark:text-blue-100">Full Breakdown</dt>
              <dd className="text-sm text-blue-800 dark:text-blue-200 mt-1">
                Most detailed report showing every payment with loan ID, date, and all amounts. Best for detailed analysis.
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </Layout>
  );
}
