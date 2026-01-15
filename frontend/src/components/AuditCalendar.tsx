'use client';

import { useState, useRef, useEffect } from 'react';
import { ChevronLeft, ChevronRight, ChevronDown } from 'lucide-react';

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

  // Month/year picker state
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [pickerYear, setPickerYear] = useState(year);
  const pickerRef = useRef<HTMLDivElement>(null);

  // Sync picker year when current month changes externally
  useEffect(() => {
    setPickerYear(year);
  }, [year]);

  // Close picker when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setIsPickerOpen(false);
      }
    };

    if (isPickerOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isPickerOpen]);

  // Handle month selection from picker
  const handleMonthSelect = (selectedMonth: number) => {
    onMonthChange(new Date(pickerYear, selectedMonth, 1));
    setIsPickerOpen(false);
  };

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

        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setIsPickerOpen(!isPickerOpen)}
            className="text-xl font-semibold text-foreground hover:text-primary transition-colors cursor-pointer flex items-center gap-1"
            aria-label="Select month and year"
          >
            {MONTHS[month]} {year}
            <ChevronDown className={`h-4 w-4 transition-transform ${isPickerOpen ? 'rotate-180' : ''}`} />
          </button>

          {/* Month/Year Picker Dropdown */}
          {isPickerOpen && (
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 bg-card border border-border rounded-xl shadow-lg p-4 z-50 min-w-[280px]">
              {/* Year selector */}
              <div className="flex items-center justify-between mb-4">
                <button
                  onClick={() => setPickerYear(y => y - 1)}
                  className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                  aria-label="Previous year"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="font-semibold text-lg">{pickerYear}</span>
                <button
                  onClick={() => setPickerYear(y => y + 1)}
                  className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                  aria-label="Next year"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>

              {/* Month grid */}
              <div className="grid grid-cols-4 gap-2">
                {MONTHS.map((monthName, idx) => {
                  const isCurrentSelection = idx === month && pickerYear === year;
                  return (
                    <button
                      key={monthName}
                      onClick={() => handleMonthSelect(idx)}
                      className={`
                        px-2 py-2 rounded-lg text-sm font-medium transition-colors
                        ${isCurrentSelection
                          ? 'bg-primary text-primary-foreground'
                          : 'hover:bg-muted text-foreground'
                        }
                      `}
                    >
                      {monthName.slice(0, 3)}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

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
