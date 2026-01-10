'use client';

import { useState, useEffect, useRef } from 'react';

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
  useEffect(() => {
    if (value) {
      const date = new Date(value);
      if (!isNaN(date.getTime())) {
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const year = date.getFullYear();
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
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          className="w-5 h-5"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5"
          />
        </svg>
      </button>
    </div>
  );
}
