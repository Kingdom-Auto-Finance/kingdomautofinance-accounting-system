'use client';

import { useState, useEffect, useMemo } from 'react';
import Layout from '@/components/Layout';
import LoanSelector from '@/components/LoanSelector';
import ColumnCustomizer from '@/components/ColumnCustomizer';
import AmortizationTable from '@/components/AmortizationTable';
import CalculationDetailsModal from '@/components/CalculationDetailsModal';
import { amortizationAPI } from '@/lib/api';
import { downloadCSV, formatDate, formatCurrency } from '@/lib/utils';
import {
  COLUMN_DEFINITIONS,
  DEFAULT_VISIBLE_COLUMNS,
  DEFAULT_COLUMN_WIDTH,
  type Loan,
  type ScheduleRow,
  type ColumnOrder,
} from '@/types/amortization';

export default function AmortizationPage() {
  // Core data
  const [loans, setLoans] = useState<Loan[]>([]);
  const [selectedLoanId, setSelectedLoanId] = useState<string>('');
  const [scheduleData, setScheduleData] = useState<ScheduleRow[]>([]);

  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortColumn, setSortColumn] = useState<string>('paymentnumber');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  // Filters and customization
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(
    DEFAULT_VISIBLE_COLUMNS
  );
  const [columnOrder, setColumnOrder] = useState<ColumnOrder[]>(
    COLUMN_DEFINITIONS.filter(col => DEFAULT_VISIBLE_COLUMNS.has(col.key)).map(col => ({
      key: col.key,
      width: DEFAULT_COLUMN_WIDTH,
    }))
  );

  // Modal
  const [selectedRow, setSelectedRow] = useState<ScheduleRow | null>(null);
  const [showCalculationModal, setShowCalculationModal] = useState(false);

  // Load loans on mount
  useEffect(() => {
    loadLoans();
  }, []);

  // Load schedule when loan selected
  useEffect(() => {
    if (selectedLoanId) {
      loadSchedule(selectedLoanId);
    } else {
      setScheduleData([]);
      setError(null);
    }
  }, [selectedLoanId]);

  // Load column preferences from localStorage
  useEffect(() => {
    try {
      const savedColumns = localStorage.getItem('amortization_visible_columns');
      const savedOrder = localStorage.getItem('amortization_column_order');

      if (savedColumns) {
        const parsed = JSON.parse(savedColumns);
        if (Array.isArray(parsed)) {
          setVisibleColumns(new Set(parsed));
        }
      }

      if (savedOrder) {
        const parsed = JSON.parse(savedOrder);
        if (Array.isArray(parsed)) {
          setColumnOrder(parsed);
        }
      }
    } catch (err) {
      console.error('Failed to load column preferences:', err);
    }
  }, []);

  // Save column preferences to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(
        'amortization_visible_columns',
        JSON.stringify(Array.from(visibleColumns))
      );
    } catch (err) {
      console.error('Failed to save column preferences:', err);
    }
  }, [visibleColumns]);

  // Save column order to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(
        'amortization_column_order',
        JSON.stringify(columnOrder)
      );
    } catch (err) {
      console.error('Failed to save column order:', err);
    }
  }, [columnOrder]);

  // Sync column order when visible columns change
  useEffect(() => {
    const currentKeys = new Set(columnOrder.map(c => c.key));
    const visibleKeys = Array.from(visibleColumns);

    // Add new visible columns that aren't in the order
    const newColumns = visibleKeys.filter(key => !currentKeys.has(key));
    if (newColumns.length > 0) {
      const newOrder = [
        ...columnOrder.filter(c => visibleColumns.has(c.key)),
        ...newColumns.map(key => ({ key, width: DEFAULT_COLUMN_WIDTH }))
      ];
      setColumnOrder(newOrder);
    } else {
      // Remove columns that are no longer visible
      const filteredOrder = columnOrder.filter(c => visibleColumns.has(c.key));
      if (filteredOrder.length !== columnOrder.length) {
        setColumnOrder(filteredOrder);
      }
    }
  }, [visibleColumns]);

  const loadLoans = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await amortizationAPI.getLoans();
      setLoans(response.data || []);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : 'Failed to load loans';
      setError(errorMessage);
      console.error('Failed to load loans:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadSchedule = async (loanId: string) => {
    setLoading(true);
    setError(null);
    setScheduleData([]);

    try {
      const response = await amortizationAPI.getSchedule(loanId);
      setScheduleData(response.data || []);
    } catch (err) {
      if (err instanceof Error) {
        if (err.message.includes('404')) {
          setError(`No schedule found for loan ${loanId}`);
        } else if (err.message.includes('500')) {
          setError('Server error. Please try again later.');
        } else {
          setError(err.message);
        }
      } else {
        setError('Failed to load schedule');
      }
      console.error('Failed to load schedule:', err);
    } finally {
      setLoading(false);
    }
  };

  // Computed: Filtered and sorted data
  const processedData = useMemo(() => {
    let filtered = scheduleData;

    // Apply status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter((row) => row.status === statusFilter);
    }

    // Apply sorting
    filtered = [...filtered].sort((a, b) => {
      const aVal = a[sortColumn as keyof ScheduleRow];
      const bVal = b[sortColumn as keyof ScheduleRow];

      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;

      const comparison = aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return filtered;
  }, [scheduleData, statusFilter, sortColumn, sortDirection]);

  const handleExportCSV = () => {
    try {
      const columns = Array.from(visibleColumns);
      const headers = columns.map(
        (key) => COLUMN_DEFINITIONS.find((c) => c.key === key)?.label || key
      );

      const rows = processedData.map((row) =>
        columns.map((key) => {
          const value = row[key as keyof ScheduleRow];
          if (value === null || value === undefined) return '';

          // Format based on column type
          const colDef = COLUMN_DEFINITIONS.find((c) => c.key === key);
          if (colDef?.format === 'currency') {
            return formatCurrency(value as number);
          }
          if (colDef?.format === 'date') {
            return formatDate(value as string);
          }
          return value.toString();
        })
      );

      const csvContent = [
        headers.join(','),
        ...rows.map((row) => row.join(','))
      ].join('\n');

      const timestamp = new Date().toISOString().split('T')[0];
      downloadCSV(
        csvContent,
        `amortization_${selectedLoanId}_${timestamp}.csv`
      );
    } catch (err) {
      console.error('Failed to export CSV:', err);
      alert('Failed to export CSV. Please try again.');
    }
  };

  const handleSort = (column: string) => {
    if (column === sortColumn) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const handleRowClick = (row: ScheduleRow) => {
    setSelectedRow(row);
    setShowCalculationModal(true);
  };

  // Get unique status values for filter dropdown
  const availableStatuses = useMemo(() => {
    const statuses = new Set(
      scheduleData.map((row) => row.status).filter(Boolean)
    );
    return Array.from(statuses).sort();
  }, [scheduleData]);

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold text-gray-900">
            Amortization Schedule Viewer
          </h1>
          <p className="mt-2 text-sm text-gray-600">
            View and analyze loan amortization schedules with detailed payment
            breakdowns
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <span className="text-red-600 text-xl">⚠️</span>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-red-800">Error</h3>
                <p className="text-sm text-red-700 mt-1">{error}</p>
              </div>
              <button
                onClick={() => setError(null)}
                className="text-red-400 hover:text-red-600"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Control Panel */}
        <div className="bg-white p-6 rounded-lg shadow">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
            {/* Loan Selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Select Loan
              </label>
              <LoanSelector
                loans={loans}
                value={selectedLoanId}
                onChange={setSelectedLoanId}
                loading={loading && loans.length === 0}
                className="w-full"
              />
            </div>

            {/* Status Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Payment Status
              </label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                disabled={!selectedLoanId || loading}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed text-gray-900"
              >
                <option value="all">All Statuses</option>
                {availableStatuses.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </div>

            {/* Column Customizer */}
            <div>
              <ColumnCustomizer
                visibleColumns={visibleColumns}
                onChange={setVisibleColumns}
              />
            </div>
          </div>
        </div>

        {/* Action Bar */}
        {scheduleData.length > 0 && (
          <div className="flex justify-between items-center">
            <div className="text-sm text-gray-600">
              Showing {processedData.length} of {scheduleData.length} payments
              {statusFilter !== 'all' && ` (filtered by ${statusFilter})`}
            </div>
            <button
              onClick={handleExportCSV}
              disabled={processedData.length === 0}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span>⬇️</span>
              Export to CSV
            </button>
          </div>
        )}

        {/* Data Table or Loading/Empty State */}
        {selectedLoanId ? (
          loading ? (
            <div className="bg-white p-12 rounded-lg shadow text-center">
              <div className="animate-spin text-4xl mb-4">⚙️</div>
              <p className="text-gray-600">Loading schedule data...</p>
            </div>
          ) : scheduleData.length === 0 ? (
            <div className="bg-white p-12 rounded-lg shadow text-center">
              <div className="text-4xl mb-4">📭</div>
              <p className="text-gray-600 font-medium">
                No schedule data found
              </p>
              <p className="text-gray-500 text-sm mt-2">
                This loan may not have an amortization schedule imported yet.
              </p>
            </div>
          ) : (
            <AmortizationTable
              data={processedData}
              columnOrder={columnOrder}
              onColumnOrderChange={setColumnOrder}
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={handleSort}
              onRowClick={handleRowClick}
            />
          )
        ) : (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-12 text-center">
            <div className="text-4xl mb-4">👆</div>
            <p className="text-blue-800 font-medium">
              Select a loan above to view its amortization schedule
            </p>
            <p className="text-blue-600 text-sm mt-2">
              {loans.length} loan{loans.length !== 1 ? 's' : ''} available
            </p>
          </div>
        )}

        {/* Calculation Details Modal */}
        {selectedRow && (
          <CalculationDetailsModal
            isOpen={showCalculationModal}
            onClose={() => setShowCalculationModal(false)}
            row={selectedRow}
          />
        )}

        {/* Legend */}
        {scheduleData.length > 0 && (
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <span>📖</span>
              Visual Indicators
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 bg-yellow-50 border border-yellow-200 rounded"></div>
                <span className="text-gray-700">Paid Late</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 bg-orange-50 border border-orange-200 rounded"></div>
                <span className="text-gray-700">Partially Paid</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 bg-red-100 border border-red-200 rounded"></div>
                <span className="text-gray-700">Amount Discrepancy</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-l-4 border-l-red-500"></div>
                <span className="text-gray-700">Balance Mismatch</span>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-3">
              💡 Click any row to view detailed calculation breakdown and
              validation checks
            </p>
          </div>
        )}
      </div>
    </Layout>
  );
}
