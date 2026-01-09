'use client';

import { useState, useEffect } from 'react';

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

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
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

  return (
    <input
      type="text"
      value={displayValue}
      onChange={handleChange}
      placeholder={placeholder}
      className={className}
      disabled={disabled}
      maxLength={10}
    />
  );
}
