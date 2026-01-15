'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';

interface AuditCalendarProps {
  currentMonth: Date;
  onMonthChange: (date: Date) => void;
  discrepancyDates: string[];
  onDateClick: (date: string) => void;
  selectedDate: string | null;
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export default function AuditCalendar({
  currentMonth,
  onMonthChange,
  discrepancyDates,
  onDateClick,
  selectedDate,
}: AuditCalendarProps) {
  const year = currentMonth.getFullYear();
  const month = currentMonth.getMonth();

  // Get first day of month and number of days
  const firstDayOfMonth = new Date(year, month, 1);
  const lastDayOfMonth = new Date(year, month + 1, 0);
  const startingDayOfWeek = firstDayOfMonth.getDay();
  const totalDays = lastDayOfMonth.getDate();

  // Create set for O(1) lookup
  const discrepancySet = new Set(discrepancyDates);

  // Navigate to previous month
  const goToPreviousMonth = () => {
    onMonthChange(new Date(year, month - 1, 1));
  };

  // Navigate to next month
  const goToNextMonth = () => {
    onMonthChange(new Date(year, month + 1, 1));
  };

  // Format date as YYYY-MM-DD
  const formatDate = (day: number): string => {
    return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  };

  // Generate calendar grid
  const generateCalendarDays = () => {
    const days = [];

    // Empty cells for days before the first of the month
    for (let i = 0; i < startingDayOfWeek; i++) {
      days.push(
        <div key={`empty-${i}`} className="h-12" />
      );
    }

    // Days of the month
    for (let day = 1; day <= totalDays; day++) {
      const dateStr = formatDate(day);
      const hasDiscrepancy = discrepancySet.has(dateStr);
      const isSelected = dateStr === selectedDate;
      const isToday = dateStr === new Date().toISOString().split('T')[0];

      days.push(
        <button
          key={day}
          onClick={() => onDateClick(dateStr)}
          className={`
            h-12 w-full rounded-lg text-sm font-medium transition-all
            flex items-center justify-center relative
            ${hasDiscrepancy
              ? 'bg-red-100 text-red-800 hover:bg-red-200 dark:bg-red-900/40 dark:text-red-200 dark:hover:bg-red-900/60'
              : 'hover:bg-muted text-foreground'
            }
            ${isSelected
              ? 'ring-2 ring-primary ring-offset-2 dark:ring-offset-background'
              : ''
            }
            ${isToday && !hasDiscrepancy
              ? 'bg-blue-50 dark:bg-blue-900/30'
              : ''
            }
          `}
        >
          {day}
          {hasDiscrepancy && (
            <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-red-500" />
          )}
        </button>
      );
    }

    return days;
  };

  return (
    <div className="bg-card rounded-xl border border-border p-6">
      {/* Header with month navigation */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={goToPreviousMonth}
          className="p-2 rounded-lg hover:bg-muted transition-colors"
          aria-label="Previous month"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>

        <h2 className="text-xl font-semibold text-foreground">
          {MONTHS[month]} {year}
        </h2>

        <button
          onClick={goToNextMonth}
          className="p-2 rounded-lg hover:bg-muted transition-colors"
          aria-label="Next month"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-1 mb-2">
        {WEEKDAYS.map((day) => (
          <div
            key={day}
            className="h-10 flex items-center justify-center text-sm font-medium text-muted-foreground"
          >
            {day}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-1">
        {generateCalendarDays()}
      </div>

      {/* Legend */}
      <div className="mt-6 flex items-center gap-6 text-sm text-muted-foreground">
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full bg-red-500" />
          <span>Has discrepancies</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full bg-blue-500" />
          <span>Today</span>
        </div>
      </div>
    </div>
  );
}
