'use client';

import { AlertTriangle, Loader2 } from 'lucide-react';
import { DiscrepancyDetail } from '@/lib/api';

interface DiscrepancyDetailsProps {
  date: string;
  discrepancies: DiscrepancyDetail[];
  loading: boolean;
}

// Format date from YYYY-MM-DD to readable format
function formatDisplayDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00');
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

// Format currency
function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

export default function DiscrepancyDetails({
  date,
  discrepancies,
  loading,
}: DiscrepancyDetailsProps) {
  if (loading) {
    return (
      <div className="bg-card rounded-xl border border-border p-6">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <span className="ml-3 text-muted-foreground">Loading discrepancies...</span>
        </div>
      </div>
    );
  }

  if (discrepancies.length === 0) {
    return (
      <div className="bg-card rounded-xl border border-border p-6">
        <h3 className="text-lg font-semibold text-foreground mb-4">
          {formatDisplayDate(date)}
        </h3>
        <div className="text-center py-12 text-muted-foreground">
          <AlertTriangle className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>No discrepancies found for this date.</p>
        </div>
      </div>
    );
  }

  // Calculate totals
  const totals = discrepancies.reduce(
    (acc, d) => ({
      payment_log_amount: acc.payment_log_amount + d.payment_log_amount,
      schedule_principal: acc.schedule_principal + d.schedule_principal,
      schedule_interest: acc.schedule_interest + d.schedule_interest,
      schedule_late_fee: acc.schedule_late_fee + d.schedule_late_fee,
      schedule_total: acc.schedule_total + d.schedule_total,
      difference: acc.difference + d.difference,
    }),
    {
      payment_log_amount: 0,
      schedule_principal: 0,
      schedule_interest: 0,
      schedule_late_fee: 0,
      schedule_total: 0,
      difference: 0,
    }
  );

  return (
    <div className="bg-card rounded-xl border border-border p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-foreground">
          {formatDisplayDate(date)}
        </h3>
        <span className="px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200">
          {discrepancies.length} discrepanc{discrepancies.length === 1 ? 'y' : 'ies'}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-3 px-4 font-medium text-muted-foreground">
                Loan ID
              </th>
              <th className="text-right py-3 px-4 font-medium text-muted-foreground">
                Payment Log
              </th>
              <th className="text-right py-3 px-4 font-medium text-muted-foreground">
                Principal
              </th>
              <th className="text-right py-3 px-4 font-medium text-muted-foreground">
                Interest
              </th>
              <th className="text-right py-3 px-4 font-medium text-muted-foreground">
                Late Fee
              </th>
              <th className="text-right py-3 px-4 font-medium text-muted-foreground">
                Schedule Total
              </th>
              <th className="text-right py-3 px-4 font-medium text-muted-foreground">
                Difference
              </th>
            </tr>
          </thead>
          <tbody>
            {discrepancies.map((d, idx) => (
              <tr
                key={`${d.loan_id}-${d.payment_log_id}-${idx}`}
                className={`
                  border-b border-border/50 hover:bg-muted/50 transition-colors
                  ${Math.abs(d.difference) > 10 ? 'bg-red-50/50 dark:bg-red-900/10' : ''}
                `}
              >
                <td className="py-3 px-4 font-medium text-foreground">
                  {d.loan_id}
                </td>
                <td className="py-3 px-4 text-right text-foreground">
                  {formatCurrency(d.payment_log_amount)}
                </td>
                <td className="py-3 px-4 text-right text-foreground">
                  {formatCurrency(d.schedule_principal)}
                </td>
                <td className="py-3 px-4 text-right text-foreground">
                  {formatCurrency(d.schedule_interest)}
                </td>
                <td className="py-3 px-4 text-right text-foreground">
                  {formatCurrency(d.schedule_late_fee)}
                </td>
                <td className="py-3 px-4 text-right text-foreground">
                  {formatCurrency(d.schedule_total)}
                </td>
                <td
                  className={`py-3 px-4 text-right font-medium ${
                    d.difference > 0
                      ? 'text-red-600 dark:text-red-400'
                      : d.difference < 0
                      ? 'text-orange-600 dark:text-orange-400'
                      : 'text-foreground'
                  }`}
                >
                  {d.difference > 0 ? '+' : ''}
                  {formatCurrency(d.difference)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-muted/50 font-semibold">
              <td className="py-3 px-4 text-foreground">Totals</td>
              <td className="py-3 px-4 text-right text-foreground">
                {formatCurrency(totals.payment_log_amount)}
              </td>
              <td className="py-3 px-4 text-right text-foreground">
                {formatCurrency(totals.schedule_principal)}
              </td>
              <td className="py-3 px-4 text-right text-foreground">
                {formatCurrency(totals.schedule_interest)}
              </td>
              <td className="py-3 px-4 text-right text-foreground">
                {formatCurrency(totals.schedule_late_fee)}
              </td>
              <td className="py-3 px-4 text-right text-foreground">
                {formatCurrency(totals.schedule_total)}
              </td>
              <td
                className={`py-3 px-4 text-right ${
                  totals.difference > 0
                    ? 'text-red-600 dark:text-red-400'
                    : totals.difference < 0
                    ? 'text-orange-600 dark:text-orange-400'
                    : 'text-foreground'
                }`}
              >
                {totals.difference > 0 ? '+' : ''}
                {formatCurrency(totals.difference)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="mt-4 text-sm text-muted-foreground">
        <p>
          <strong>Positive difference:</strong> Payment log amount is greater than schedule total (overpayment or missing allocation)
        </p>
        <p>
          <strong>Negative difference:</strong> Schedule total exceeds payment log amount (over-allocation)
        </p>
      </div>
    </div>
  );
}
