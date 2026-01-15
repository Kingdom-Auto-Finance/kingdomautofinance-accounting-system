'use client';

import { useState, useEffect, useCallback } from 'react';
import Layout from '@/components/Layout';
import AuditCalendar from '@/components/AuditCalendar';
import DiscrepancyDetails from '@/components/DiscrepancyDetails';
import {
  auditAPI,
  DiscrepancyDetail,
  MonthlyDiscrepanciesResponse,
} from '@/lib/api';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';

export default function AuditPage() {
  // State for current month view
  const [currentMonth, setCurrentMonth] = useState(() => new Date());

  // State for monthly discrepancy data
  const [monthlyData, setMonthlyData] = useState<MonthlyDiscrepanciesResponse | null>(null);
  const [monthlyLoading, setMonthlyLoading] = useState(false);
  const [monthlyError, setMonthlyError] = useState<string | null>(null);

  // State for selected date details
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [discrepancies, setDiscrepancies] = useState<DiscrepancyDetail[]>([]);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);

  // Fetch monthly discrepancies when month changes
  const fetchMonthlyDiscrepancies = useCallback(async () => {
    setMonthlyLoading(true);
    setMonthlyError(null);

    try {
      const year = currentMonth.getFullYear();
      const month = currentMonth.getMonth() + 1; // API expects 1-12
      const data = await auditAPI.monthlyDiscrepancies(year, month);
      setMonthlyData(data);

      // Clear selection when month changes
      setSelectedDate(null);
      setDiscrepancies([]);
    } catch (error) {
      console.error('Failed to fetch monthly discrepancies:', error);
      setMonthlyError(error instanceof Error ? error.message : 'Failed to fetch data');
      setMonthlyData(null);
    } finally {
      setMonthlyLoading(false);
    }
  }, [currentMonth]);

  // Fetch date discrepancies when a date is selected
  const fetchDateDiscrepancies = useCallback(async (date: string) => {
    setDetailsLoading(true);
    setDetailsError(null);

    try {
      const data = await auditAPI.dateDiscrepancies(date);
      setDiscrepancies(data.discrepancies);
    } catch (error) {
      console.error('Failed to fetch date discrepancies:', error);
      setDetailsError(error instanceof Error ? error.message : 'Failed to fetch data');
      setDiscrepancies([]);
    } finally {
      setDetailsLoading(false);
    }
  }, []);

  // Load monthly data on mount and when month changes
  useEffect(() => {
    fetchMonthlyDiscrepancies();
  }, [fetchMonthlyDiscrepancies]);

  // Load date details when selection changes
  useEffect(() => {
    if (selectedDate) {
      fetchDateDiscrepancies(selectedDate);
    }
  }, [selectedDate, fetchDateDiscrepancies]);

  // Handle date click
  const handleDateClick = (date: string) => {
    setSelectedDate(date);
  };

  // Handle month change
  const handleMonthChange = (date: Date) => {
    setCurrentMonth(date);
  };

  return (
    <Layout>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Database Audit</h1>
            <p className="text-muted-foreground mt-1">
              Review payment discrepancies between payments log and amortization schedules
            </p>
          </div>

          <button
            onClick={fetchMonthlyDiscrepancies}
            disabled={monthlyLoading}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`h-4 w-4 ${monthlyLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Summary Cards */}
        {monthlyData && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-card rounded-xl border border-border p-6">
              <p className="text-sm text-muted-foreground">Days with Discrepancies</p>
              <p className="text-3xl font-bold text-foreground mt-2">
                {monthlyData.discrepancy_dates.length}
              </p>
            </div>

            <div className="bg-card rounded-xl border border-border p-6">
              <p className="text-sm text-muted-foreground">Total Discrepancies</p>
              <p className="text-3xl font-bold text-red-600 dark:text-red-400 mt-2">
                {monthlyData.summary.total_discrepancies}
              </p>
            </div>

            <div className="bg-card rounded-xl border border-border p-6">
              <p className="text-sm text-muted-foreground">Affected Loans</p>
              <p className="text-3xl font-bold text-orange-600 dark:text-orange-400 mt-2">
                {monthlyData.summary.total_affected_loans}
              </p>
            </div>
          </div>
        )}

        {/* Error State */}
        {monthlyError && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-6">
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-6 w-6 text-red-600 dark:text-red-400" />
              <div>
                <p className="font-medium text-red-800 dark:text-red-200">
                  Failed to load audit data
                </p>
                <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                  {monthlyError}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Loading State */}
        {monthlyLoading && !monthlyData && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <span className="ml-3 text-muted-foreground">Loading audit data...</span>
          </div>
        )}

        {/* Main Content */}
        {!monthlyLoading && monthlyData && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Calendar */}
            <AuditCalendar
              currentMonth={currentMonth}
              onMonthChange={handleMonthChange}
              discrepancyDates={monthlyData.discrepancy_dates}
              onDateClick={handleDateClick}
              selectedDate={selectedDate}
            />

            {/* Discrepancy Details */}
            {selectedDate ? (
              <DiscrepancyDetails
                date={selectedDate}
                discrepancies={discrepancies}
                loading={detailsLoading}
              />
            ) : (
              <div className="bg-card rounded-xl border border-border p-6">
                <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-center">
                  <AlertTriangle className="h-12 w-12 text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground">
                    Select a date from the calendar to view discrepancy details
                  </p>
                  {monthlyData.discrepancy_dates.length > 0 && (
                    <p className="text-sm text-muted-foreground mt-2">
                      Red highlighted dates have payment discrepancies
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Details Error */}
        {detailsError && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4">
            <p className="text-sm text-red-600 dark:text-red-400">
              Failed to load discrepancy details: {detailsError}
            </p>
          </div>
        )}
      </div>
    </Layout>
  );
}
