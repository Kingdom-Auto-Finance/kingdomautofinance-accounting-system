'use client';

import { useState, useEffect, useRef } from 'react';
import { Calendar } from 'lucide-react';

interface DateInputProps {
  value: string; // ISO format (YYYY-MM-DD)
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export default function DateInput({
  value,
  onChange,
  placeholder = 'mm/dd/yyyy',
  className = '',
  disabled = false,
}: DateInputProps) {
  // Display value in mm/dd/yyyy format
  const [displayValue, setDisplayValue] = useState('');
  const datePickerRef = useRef<HTMLInputElement>(null);

  // Convert ISO format to mm/dd/yyyy for display
  // Parse ISO string directly without Date object to avoid timezone issues
  useEffect(() => {
    if (value) {
      // Parse ISO date string directly (YYYY-MM-DD format)
      const parts = value.split('-');
      if (parts.length === 3) {
        const year = parts[0];
        const month = parts[1];
        const day = parts[2].split('T')[0]; // Handle YYYY-MM-DDTHH:mm:ss format
        setDisplayValue(`${month}/${day}/${year}`);
      }
    } else {
      setDisplayValue('');
    }
  }, [value]);

  const formatAsYouType = (input: string): string => {
    // Remove all non-digits
    const digits = input.replace(/\D/g, '');

    // Format as mm/dd/yyyy
    if (digits.length <= 2) {
      return digits;
    } else if (digits.length <= 4) {
      return `${digits.slice(0, 2)}/${digits.slice(2)}`;
    } else {
      return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4, 8)}`;
    }
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target.value;
    const formatted = formatAsYouType(input);
    setDisplayValue(formatted);

    // Convert to ISO format if complete
    if (formatted.length === 10) {
      const digits = formatted.replace(/\D/g, '');
      const month = digits.substring(0, 2);
      const day = digits.substring(2, 4);
      const year = digits.substring(4, 8);

      // Validate the date
      const isoDate = `${year}-${month}-${day}`;
      const date = new Date(isoDate);

      if (!isNaN(date.getTime())) {
        onChange(isoDate);
      }
    } else if (formatted.length === 0) {
      onChange('');
    }
  };

  const handleDatePickerChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const isoDate = e.target.value;
    if (isoDate) {
      onChange(isoDate);
    }
  };

  const openDatePicker = () => {
    if (datePickerRef.current && !disabled) {
      datePickerRef.current.showPicker?.();
    }
  };

  return (
    <div className="relative">
      <input
        type="text"
        value={displayValue}
        onChange={handleTextChange}
        placeholder={placeholder}
        className={className}
        disabled={disabled}
        maxLength={10}
      />
      {/* Hidden native date picker */}
      <input
        ref={datePickerRef}
        type="date"
        value={value}
        onChange={handleDatePickerChange}
        className="absolute inset-0 opacity-0 cursor-pointer pointer-events-none"
        disabled={disabled}
        tabIndex={-1}
      />
      {/* Calendar icon */}
      <button
        type="button"
        onClick={openDatePicker}
        disabled={disabled}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground disabled:opacity-50"
        tabIndex={-1}
      >
        <Calendar className="w-5 h-5" />
      </button>
    </div>
  );
}
