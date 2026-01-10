'use client';

import { useMemo } from 'react';
import { COLUMN_DEFINITIONS, type ScheduleRow } from '@/types/amortization';
import { formatCurrency, formatDate } from '@/lib/utils';

interface AmortizationTableProps {
  data: ScheduleRow[];
  visibleColumns: Set<string>;
  sortColumn: string;
  sortDirection: 'asc' | 'desc';
  onSort: (column: string) => void;
  onRowClick: (row: ScheduleRow) => void;
}

export default function AmortizationTable({
  data,
  visibleColumns,
  sortColumn,
  sortDirection,
  onSort,
  onRowClick,
}: AmortizationTableProps) {
  const visibleColumnDefs = useMemo(
    () => COLUMN_DEFINITIONS.filter((col) => visibleColumns.has(col.key)),
    [visibleColumns]
  );

  const calculateDiscrepancies = (row: ScheduleRow) => {
    // Balance discrepancy
    const balanceDiscrepancy = Math.abs(
      row.endingbalance - row.scheduledfinalbalance
    );

    // Payment discrepancy
    const paymentDiscrepancy =
      row.actualpaymentamount !== null
        ? Math.abs(row.actualpaymentamount - row.scheduledpayment)
        : 0;

    // Allocation discrepancy (payment should equal sum of parts)
    const allocationDiscrepancy =
      row.actualpaymentamount !== null
        ? Math.abs(
            row.actualpaymentamount -
              ((row.principalpaid || 0) +
                (row.interestpaid || 0) +
                (row.latefee || 0) -
                (row.creditapplied || 0))
          )
        : 0;

    return {
      hasBalanceDiscrepancy: balanceDiscrepancy > 0.01,
      hasPaymentDiscrepancy:
        row.actualpaymentamount !== null && paymentDiscrepancy > 0.01,
      hasAllocationDiscrepancy: allocationDiscrepancy > 0.01,
    };
  };

  const getRowClassName = (row: ScheduleRow) => {
    const classes = [
      'border-b',
      'hover:bg-gray-50',
      'cursor-pointer',
      'transition-colors',
    ];

    // Highlight late payments
    if (row.status === 'Paid Late') {
      classes.push('bg-yellow-50');
    }

    // Highlight partial payments
    if (row.status === 'Partially Paid') {
      classes.push('bg-orange-50');
    }

    // Highlight discrepancies with left border
    const discrepancies = calculateDiscrepancies(row);
    if (
      discrepancies.hasBalanceDiscrepancy ||
      discrepancies.hasAllocationDiscrepancy
    ) {
      classes.push('border-l-4', 'border-l-red-500');
    }

    return classes.join(' ');
  };

  const getCellClassName = (row: ScheduleRow, columnKey: keyof ScheduleRow) => {
    const classes = ['px-4', 'py-3', 'text-sm'];

    const discrepancies = calculateDiscrepancies(row);

    // Highlight specific discrepancy cells
    if (columnKey === 'endingbalance' && discrepancies.hasBalanceDiscrepancy) {
      classes.push('bg-red-100', 'font-semibold', 'text-red-900');
    }

    if (
      columnKey === 'actualpaymentamount' &&
      discrepancies.hasPaymentDiscrepancy
    ) {
      classes.push('bg-red-100', 'font-semibold', 'text-red-900');
    }

    return classes.join(' ');
  };

  const formatCellValue = (
    row: ScheduleRow,
    col: typeof COLUMN_DEFINITIONS[0]
  ) => {
    const value = row[col.key];

    if (value === null || value === undefined) {
      return <span className="text-gray-400">—</span>;
    }

    switch (col.format) {
      case 'currency':
        return formatCurrency(value as number);
      case 'date':
        try {
          return formatDate(value as string);
        } catch {
          return <span className="text-gray-400">Invalid date</span>;
        }
      case 'number':
        return value.toString();
      case 'text':
        return getStatusBadge(value as string);
      default:
        return value.toString();
    }
  };

  const getStatusBadge = (status: string) => {
    let colorClasses = 'bg-gray-100 text-gray-800';

    if (status === 'Paid') {
      colorClasses = 'bg-green-100 text-green-800';
    } else if (status === 'Paid Late') {
      colorClasses = 'bg-yellow-100 text-yellow-800';
    } else if (status === 'Partially Paid') {
      colorClasses = 'bg-orange-100 text-orange-800';
    } else if (status === 'Paid Off' || status === 'Paid Off Late') {
      colorClasses = 'bg-blue-100 text-blue-800';
    } else if (status === 'Pending' || !status) {
      colorClasses = 'bg-gray-100 text-gray-600';
    }

    return (
      <span
        className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${colorClasses}`}
      >
        {status || 'Pending'}
      </span>
    );
  };

  const getSortIcon = (columnKey: string) => {
    if (sortColumn !== columnKey) {
      return (
        <svg
          className="w-4 h-4 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
          />
        </svg>
      );
    }

    return sortDirection === 'asc' ? (
      <svg
        className="w-4 h-4 text-blue-600"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M5 15l7-7 7 7"
        />
      </svg>
    ) : (
      <svg
        className="w-4 h-4 text-blue-600"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M19 9l-7 7-7-7"
        />
      </svg>
    );
  };

  if (visibleColumnDefs.length === 0) {
    return (
      <div className="bg-white p-12 rounded-lg shadow text-center">
        <p className="text-gray-600">
          Please select at least one column to display
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {visibleColumnDefs.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none"
                  onClick={() => onSort(col.key)}
                >
                  <div className="flex items-center gap-2">
                    <span>{col.label}</span>
                    {getSortIcon(col.key)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {data.length === 0 ? (
              <tr>
                <td
                  colSpan={visibleColumnDefs.length}
                  className="px-4 py-12 text-center text-gray-500"
                >
                  No data available
                </td>
              </tr>
            ) : (
              data.map((row, idx) => (
                <tr
                  key={`${row.paymentnumber}-${idx}`}
                  className={getRowClassName(row)}
                  onClick={() => onRowClick(row)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onRowClick(row);
                    }
                  }}
                >
                  {visibleColumnDefs.map((col) => (
                    <td key={col.key} className={getCellClassName(row, col.key)}>
                      {formatCellValue(row, col)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
