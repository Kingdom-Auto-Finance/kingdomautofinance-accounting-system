'use client';

import { useMemo, useState, useRef, useEffect } from 'react';
import { COLUMN_DEFINITIONS, type ScheduleRow, type ColumnOrder, DEFAULT_COLUMN_WIDTH } from '@/types/amortization';
import { formatCurrency, formatDate } from '@/lib/utils';

interface AmortizationTableProps {
  data: ScheduleRow[];
  columnOrder: ColumnOrder[];
  onColumnOrderChange: (newOrder: ColumnOrder[]) => void;
  sortColumn: string;
  sortDirection: 'asc' | 'desc';
  onSort: (column: string) => void;
  onRowClick: (row: ScheduleRow) => void;
}

export default function AmortizationTable({
  data,
  columnOrder,
  onColumnOrderChange,
  sortColumn,
  sortDirection,
  onSort,
  onRowClick,
}: AmortizationTableProps) {
  const [draggedColumn, setDraggedColumn] = useState<string | null>(null);
  const [resizingColumn, setResizingColumn] = useState<string | null>(null);
  const [resizeStartX, setResizeStartX] = useState(0);
  const [resizeStartWidth, setResizeStartWidth] = useState(0);

  const visibleColumnDefs = useMemo(
    () => columnOrder.map(order => {
      const def = COLUMN_DEFINITIONS.find(col => col.key === order.key);
      return { ...def!, ...order };
    }).filter(col => col !== undefined),
    [columnOrder]
  );

  const calculateDiscrepancies = (row: ScheduleRow) => {
    const balanceDiscrepancy = Math.abs(
      row.endingbalance - row.scheduledfinalbalance
    );

    const paymentDiscrepancy =
      row.actualpaymentamount !== null
        ? Math.abs(row.actualpaymentamount - row.scheduledpayment)
        : 0;

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

    if (row.status === 'Paid Late') {
      classes.push('bg-yellow-50');
    }

    if (row.status === 'Partially Paid') {
      classes.push('bg-orange-50');
    }

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
    const classes = ['px-4', 'py-3', 'text-sm', 'text-gray-900'];

    const discrepancies = calculateDiscrepancies(row);

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
    col: typeof visibleColumnDefs[0]
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

  // Drag and drop handlers
  const handleDragStart = (e: React.DragEvent, columnKey: string) => {
    setDraggedColumn(columnKey);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e: React.DragEvent, targetColumnKey: string) => {
    e.preventDefault();

    if (!draggedColumn || draggedColumn === targetColumnKey) {
      setDraggedColumn(null);
      return;
    }

    const newOrder = [...columnOrder];
    const draggedIndex = newOrder.findIndex(c => c.key === draggedColumn);
    const targetIndex = newOrder.findIndex(c => c.key === targetColumnKey);

    if (draggedIndex !== -1 && targetIndex !== -1) {
      const [removed] = newOrder.splice(draggedIndex, 1);
      newOrder.splice(targetIndex, 0, removed);
      onColumnOrderChange(newOrder);
    }

    setDraggedColumn(null);
  };

  // Resize handlers
  const handleResizeStart = (e: React.MouseEvent, columnKey: string) => {
    e.preventDefault();
    e.stopPropagation();

    const column = columnOrder.find(c => c.key === columnKey);
    if (column) {
      setResizingColumn(columnKey);
      setResizeStartX(e.clientX);
      setResizeStartWidth(column.width || DEFAULT_COLUMN_WIDTH);
    }
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (resizingColumn) {
        const diff = e.clientX - resizeStartX;
        const newWidth = Math.max(80, resizeStartWidth + diff);

        const newOrder = columnOrder.map(col =>
          col.key === resizingColumn ? { ...col, width: newWidth } : col
        );
        onColumnOrderChange(newOrder);
      }
    };

    const handleMouseUp = () => {
      if (resizingColumn) {
        setResizingColumn(null);
      }
    };

    if (resizingColumn) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [resizingColumn, resizeStartX, resizeStartWidth, columnOrder, onColumnOrderChange]);

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
                  draggable
                  onDragStart={(e) => handleDragStart(e, col.key)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, col.key)}
                  style={{ width: col.width || DEFAULT_COLUMN_WIDTH }}
                  className={`px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors select-none relative group ${
                    draggedColumn === col.key ? 'opacity-50' : ''
                  }`}
                  onClick={() => onSort(col.key)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <svg
                        className="w-3 h-3 text-gray-400 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M4 8h16M4 16h16"
                        />
                      </svg>
                      <span className="truncate">{col.label}</span>
                    </div>
                    {getSortIcon(col.key)}
                  </div>

                  {/* Resize handle */}
                  <div
                    className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-blue-500 group-hover:opacity-100 opacity-0 transition-opacity"
                    onMouseDown={(e) => handleResizeStart(e, col.key)}
                    onClick={(e) => e.stopPropagation()}
                  />
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

      {/* Instructions */}
      <div className="px-4 py-2 bg-gray-50 border-t border-gray-200">
        <p className="text-xs text-gray-500 text-center">
          💡 Drag column headers to reorder • Drag right edge to resize • Click header to sort
        </p>
      </div>
    </div>
  );
}
