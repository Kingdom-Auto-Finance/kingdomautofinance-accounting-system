'use client';

import { useEffect } from 'react';
import { type ScheduleRow, type PaymentValidation } from '@/types/amortization';
import { formatCurrency, formatDate } from '@/lib/utils';

interface CalculationDetailsModalProps {
  isOpen: boolean;
  onClose: () => void;
  row: ScheduleRow;
}

export default function CalculationDetailsModal({
  isOpen,
  onClose,
  row,
}: CalculationDetailsModalProps) {
  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const validatePayment = (): PaymentValidation => {
    // Allocation check: actualpaymentamount = principalpaid + interestpaid + latefee - creditapplied
    const expectedAllocation =
      (row.principalpaid || 0) +
      (row.interestpaid || 0) +
      (row.latefee || 0) -
      (row.creditapplied || 0);
    const actualAllocation = row.actualpaymentamount || 0;
    const allocationDiff = Math.abs(actualAllocation - expectedAllocation);

    // Balance check: endingbalance should match scheduledfinalbalance (or close to it)
    const expectedBalance = row.scheduledfinalbalance;
    const actualBalance = row.endingbalance;
    const balanceDiff = Math.abs(actualBalance - expectedBalance);

    return {
      allocationCheck: {
        isValid: allocationDiff < 0.01,
        expected: expectedAllocation,
        actual: actualAllocation,
        diff: actualAllocation - expectedAllocation,
      },
      balanceCheck: {
        isValid: balanceDiff < 0.01,
        expected: expectedBalance,
        actual: actualBalance,
        diff: actualBalance - expectedBalance,
      },
    };
  };

  const validation = validatePayment();

  const calculateDaysLate = () => {
    if (!row.actualpaymentdate || !row.duedate) return null;
    try {
      const actual = new Date(row.actualpaymentdate);
      const due = new Date(row.duedate);
      const diffTime = actual.getTime() - due.getTime();
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      return diffDays > 0 ? diffDays : 0;
    } catch {
      return null;
    }
  };

  const daysLate = calculateDaysLate();

  const getValidationIcon = (isValid: boolean) => {
    return isValid ? (
      <span className="text-green-600 font-bold">✓</span>
    ) : (
      <span className="text-red-600 font-bold">✗</span>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto"
      aria-labelledby="modal-title"
      role="dialog"
      aria-modal="true"
    >
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
            <div>
              <h2 id="modal-title" className="text-xl font-bold text-gray-900">
                Payment Calculation Details
              </h2>
              <p className="text-sm text-gray-600 mt-1">
                Payment #{row.paymentnumber} • Due:{' '}
                {formatDate(row.duedate)}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
              aria-label="Close modal"
            >
              <svg
                className="w-6 h-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4 space-y-6">
            {/* Scheduled Amounts Section */}
            <div className="bg-blue-50 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-blue-900 mb-3 flex items-center gap-2">
                <span>📋</span>
                SCHEDULED AMOUNTS
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-blue-800">Scheduled Payment:</span>
                  <span className="font-mono font-semibold text-blue-900">
                    {formatCurrency(row.scheduledpayment)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-blue-800">Scheduled Principal:</span>
                  <span className="font-mono text-blue-900">
                    {formatCurrency(row.scheduledprincipal)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-blue-800">Scheduled Interest:</span>
                  <span className="font-mono text-blue-900">
                    {formatCurrency(row.scheduledinterest)}
                  </span>
                </div>
                <div className="flex justify-between pt-2 border-t border-blue-200">
                  <span className="text-blue-800">
                    Scheduled Final Balance:
                  </span>
                  <span className="font-mono font-semibold text-blue-900">
                    {formatCurrency(row.scheduledfinalbalance)}
                  </span>
                </div>
              </div>
            </div>

            {/* Actual Amounts Section */}
            <div className="bg-green-50 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-green-900 mb-3 flex items-center gap-2">
                <span>✅</span>
                ACTUAL AMOUNTS
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-green-800">Actual Payment:</span>
                  <span className="font-mono font-semibold text-green-900">
                    {row.actualpaymentamount !== null
                      ? formatCurrency(row.actualpaymentamount)
                      : 'N/A'}
                    {row.actualpaymentamount !== null && (
                      <span className="ml-2 text-xs">
                        (
                        {row.actualpaymentamount > row.scheduledpayment
                          ? `+${formatCurrency(row.actualpaymentamount - row.scheduledpayment)} over`
                          : row.actualpaymentamount < row.scheduledpayment
                            ? `${formatCurrency(row.actualpaymentamount - row.scheduledpayment)} short`
                            : 'exact'}
                        )
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-green-800">Principal Paid:</span>
                  <span className="font-mono text-green-900">
                    {row.principalpaid !== null
                      ? formatCurrency(row.principalpaid)
                      : 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-green-800">Interest Paid:</span>
                  <span className="font-mono text-green-900">
                    {row.interestpaid !== null
                      ? formatCurrency(row.interestpaid)
                      : 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-green-800">Late Fee:</span>
                  <span className="font-mono text-green-900">
                    {row.latefee !== null
                      ? formatCurrency(row.latefee)
                      : formatCurrency(0)}
                  </span>
                </div>
                {row.creditapplied !== null && row.creditapplied !== 0 && (
                  <div className="flex justify-between">
                    <span className="text-green-800">Credit Applied:</span>
                    <span className="font-mono text-green-900">
                      {formatCurrency(row.creditapplied)}
                    </span>
                  </div>
                )}
                <div className="flex justify-between pt-2 border-t border-green-200">
                  <span className="text-green-800">Ending Balance:</span>
                  <span className="font-mono font-semibold text-green-900">
                    {formatCurrency(row.endingbalance)}
                  </span>
                </div>
              </div>
            </div>

            {/* Payment Allocation Validation */}
            <div
              className={`rounded-lg p-4 ${
                validation.allocationCheck.isValid
                  ? 'bg-green-50 border border-green-200'
                  : 'bg-red-50 border border-red-200'
              }`}
            >
              <h3
                className={`text-sm font-semibold mb-3 flex items-center gap-2 ${
                  validation.allocationCheck.isValid
                    ? 'text-green-900'
                    : 'text-red-900'
                }`}
              >
                {getValidationIcon(validation.allocationCheck.isValid)}
                PAYMENT ALLOCATION VALIDATION
              </h3>
              <div className="space-y-2 text-sm">
                <div
                  className={
                    validation.allocationCheck.isValid
                      ? 'text-green-800'
                      : 'text-red-800'
                  }
                >
                  <div className="font-mono text-xs bg-white p-2 rounded border border-gray-200">
                    {formatCurrency(validation.allocationCheck.actual)} ={' '}
                    {formatCurrency(row.principalpaid || 0)} +{' '}
                    {formatCurrency(row.interestpaid || 0)} +{' '}
                    {formatCurrency(row.latefee || 0)}
                    {row.creditapplied && row.creditapplied !== 0
                      ? ` - ${formatCurrency(row.creditapplied)}`
                      : ''}
                  </div>
                  <div className="mt-2 text-xs">
                    <strong>Formula:</strong> Actual Payment = Principal Paid +
                    Interest Paid + Late Fee - Credit Applied
                  </div>
                  {!validation.allocationCheck.isValid && (
                    <div className="mt-2 p-2 bg-red-100 rounded">
                      <strong>Discrepancy:</strong>{' '}
                      {formatCurrency(Math.abs(validation.allocationCheck.diff))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Balance Validation */}
            <div
              className={`rounded-lg p-4 ${
                validation.balanceCheck.isValid
                  ? 'bg-green-50 border border-green-200'
                  : 'bg-red-50 border border-red-200'
              }`}
            >
              <h3
                className={`text-sm font-semibold mb-3 flex items-center gap-2 ${
                  validation.balanceCheck.isValid
                    ? 'text-green-900'
                    : 'text-red-900'
                }`}
              >
                {getValidationIcon(validation.balanceCheck.isValid)}
                BALANCE PROGRESSION VALIDATION
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span
                    className={
                      validation.balanceCheck.isValid
                        ? 'text-green-800'
                        : 'text-red-800'
                    }
                  >
                    Starting Balance:
                  </span>
                  <span className="font-mono">
                    {formatCurrency(row.scheduledbalance)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span
                    className={
                      validation.balanceCheck.isValid
                        ? 'text-green-800'
                        : 'text-red-800'
                    }
                  >
                    Less: Principal Paid:
                  </span>
                  <span className="font-mono">
                    -{formatCurrency(row.principalpaid || 0)}
                  </span>
                </div>
                <div className="flex justify-between pt-2 border-t border-gray-300">
                  <span
                    className={
                      validation.balanceCheck.isValid
                        ? 'text-green-800'
                        : 'text-red-800'
                    }
                  >
                    Actual Ending Balance:
                  </span>
                  <span className="font-mono font-semibold">
                    {formatCurrency(validation.balanceCheck.actual)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span
                    className={
                      validation.balanceCheck.isValid
                        ? 'text-green-800'
                        : 'text-red-800'
                    }
                  >
                    Expected Ending Balance:
                  </span>
                  <span className="font-mono font-semibold">
                    {formatCurrency(validation.balanceCheck.expected)}
                  </span>
                </div>
                {!validation.balanceCheck.isValid && (
                  <div className="mt-2 p-2 bg-red-100 rounded">
                    <strong>Discrepancy:</strong>{' '}
                    {formatCurrency(validation.balanceCheck.diff)}
                    <div className="mt-2 text-xs">
                      <strong>Possible causes:</strong>
                      <ul className="list-disc ml-4 mt-1">
                        <li>Manual adjustment in database</li>
                        <li>Rounding error from payment processor</li>
                        <li>Credit or refund applied outside normal flow</li>
                        <li>Data migration discrepancy</li>
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Payment Status Section */}
            <div className="bg-gray-50 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                <span>📊</span>
                PAYMENT STATUS
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-800">Status:</span>
                  <span className="font-semibold text-gray-900">
                    {row.status || 'Pending'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-800">Due Date:</span>
                  <span className="font-mono text-gray-900">
                    {formatDate(row.duedate)}
                  </span>
                </div>
                {row.actualpaymentdate && (
                  <div className="flex justify-between">
                    <span className="text-gray-800">Payment Date:</span>
                    <span className="font-mono text-gray-900">
                      {formatDate(row.actualpaymentdate)}
                    </span>
                  </div>
                )}
                {daysLate !== null && daysLate > 0 && (
                  <div className="flex justify-between pt-2 border-t border-gray-300">
                    <span className="text-gray-800">Days Late:</span>
                    <span className="font-semibold text-red-600">
                      {daysLate} {daysLate === 1 ? 'day' : 'days'}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="sticky bottom-0 bg-gray-50 border-t border-gray-200 px-6 py-4">
            <button
              onClick={onClose}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
