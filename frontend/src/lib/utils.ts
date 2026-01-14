import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes with proper conflict resolution
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format currency values
 */
export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

/**
 * Format dates as mm/dd/yyyy
 * Handles ISO strings directly to avoid timezone issues
 */
export function formatDate(date: Date | string): string {
  // If it's an ISO string (YYYY-MM-DD), parse directly to avoid timezone issues
  if (typeof date === 'string' && /^\d{4}-\d{2}-\d{2}/.test(date)) {
    const datePart = date.split('T')[0];
    const parts = datePart.split('-');
    return `${parts[1]}/${parts[2]}/${parts[0]}`;
  }
  // For Date objects, use UTC methods to avoid timezone shift
  const d = new Date(date);
  const month = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  const year = d.getUTCFullYear();
  return `${month}/${day}/${year}`;
}

/**
 * Parse mm/dd/yyyy format to ISO format (YYYY-MM-DD)
 */
export function parseDate(mmddyyyy: string): string {
  if (!mmddyyyy || mmddyyyy.length < 8) return '';

  // Remove any non-digit characters
  const digits = mmddyyyy.replace(/\D/g, '');
  if (digits.length < 8) return '';

  const month = digits.substring(0, 2);
  const day = digits.substring(2, 4);
  const year = digits.substring(4, 8);

  return `${year}-${month}-${day}`;
}

/**
 * Validate date string in mm/dd/yyyy format
 */
export function isValidDate(dateString: string): boolean {
  if (!dateString) return false;

  // Check format: mm/dd/yyyy
  const regex = /^(0[1-9]|1[0-2])\/(0[1-9]|[12][0-9]|3[01])\/\d{4}$/;
  if (!regex.test(dateString)) return false;

  // Check if it's a valid date
  const isoDate = parseDate(dateString);
  const date = new Date(isoDate);
  return date instanceof Date && !isNaN(date.getTime());
}

/*
 * Format date with time
 */
export function formatDateTime(date: Date | string): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date));
}

/**
 * Download CSV file
 */
export function downloadCSV(csvContent: string, filename: string) {
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  if (link.download !== undefined) {
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }
}
