'use client';

import { useState, useMemo, useRef, useEffect } from 'react';
import { Loan } from '@/types/amortization';

interface LoanSelectorProps {
  loans: Loan[];
  value: string;
  onChange: (loanId: string) => void;
  loading?: boolean;
  className?: string;
}

export default function LoanSelector({
  loans,
  value,
  onChange,
  loading = false,
  className = '',
}: LoanSelectorProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const selectedLoan = useMemo(
    () => loans.find((loan) => loan.loan_id === value),
    [loans, value]
  );

  const filteredLoans = useMemo(() => {
    if (!searchTerm) return loans;
    const term = searchTerm.toLowerCase();
    return loans.filter(
      (loan) =>
        loan.loan_id.toLowerCase().includes(term) ||
        loan.customer_name?.toLowerCase().includes(term) ||
        loan.vehicle_info?.toLowerCase().includes(term)
    );
  }, [loans, searchTerm]);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [isOpen]);

  // Reset highlighted index when filtered loans change
  useEffect(() => {
    setHighlightedIndex(0);
  }, [filteredLoans]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setSearchTerm('');
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (loanId: string) => {
    onChange(loanId);
    setIsOpen(false);
    setSearchTerm('');
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onChange('');
    setSearchTerm('');
    setIsOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev < filteredLoans.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (filteredLoans[highlightedIndex]) {
          handleSelect(filteredLoans[highlightedIndex].loan_id);
        }
        break;
      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        setSearchTerm('');
        break;
    }
  };

  const displayText = selectedLoan
    ? `${selectedLoan.loan_id}${
        selectedLoan.customer_name ? ` - ${selectedLoan.customer_name}` : ''
      }${selectedLoan.vehicle_info ? ` - ${selectedLoan.vehicle_info}` : ''}`
    : 'Select a loan...';

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      {/* Selected value display / trigger */}
      <div className="relative">
        <button
          type="button"
          onClick={() => !loading && setIsOpen(!isOpen)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          className={`w-full px-4 py-2 text-left border border-input rounded-lg bg-card focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors text-foreground ${
            loading ? 'opacity-50 cursor-not-allowed' : 'hover:border-muted-foreground'
          }`}
        >
          <span className={value ? 'text-foreground' : 'text-muted-foreground'}>
            {loading ? 'Loading loans...' : displayText}
          </span>
        </button>

        {/* Clear button */}
        {value && !loading && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-10 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-1"
            aria-label="Clear selection"
          >
            ✕
          </button>
        )}

        {/* Dropdown arrow */}
        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
          <svg
            className={`w-5 h-5 text-muted-foreground transition-transform ${
              isOpen ? 'rotate-180' : ''
            }`}
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
        </div>
      </div>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute z-50 w-full mt-2 bg-card border border-border rounded-lg shadow-lg max-h-96 flex flex-col">
          {/* Search input */}
          <div className="p-3 border-b border-border">
            <div className="relative">
              <input
                ref={searchInputRef}
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type to search loans..."
                className="w-full pl-9 pr-3 py-2 border border-input rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm text-foreground placeholder-muted-foreground bg-card"
              />
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </div>
          </div>

          {/* Loan list */}
          <div className="overflow-y-auto">
            {filteredLoans.length === 0 ? (
              <div className="px-4 py-8 text-center text-muted-foreground text-sm">
                {searchTerm ? 'No matching loans found' : 'No loans available'}
              </div>
            ) : (
              filteredLoans.map((loan, index) => (
                <button
                  key={loan.loan_id}
                  type="button"
                  onClick={() => handleSelect(loan.loan_id)}
                  onMouseEnter={() => setHighlightedIndex(index)}
                  className={`w-full px-4 py-3 text-left transition-colors border-b border-border last:border-b-0 ${
                    index === highlightedIndex
                      ? 'bg-blue-100 dark:bg-blue-950'
                      : loan.loan_id === value
                        ? 'bg-blue-50 dark:bg-blue-950/50'
                        : 'hover:bg-muted'
                  }`}
                >
                  <div className="font-medium text-foreground">
                    {loan.loan_id}
                  </div>
                  {(loan.customer_name || loan.vehicle_info) && (
                    <div className="text-sm text-muted-foreground mt-1">
                      {loan.customer_name && <span>{loan.customer_name}</span>}
                      {loan.customer_name && loan.vehicle_info && (
                        <span> • </span>
                      )}
                      {loan.vehicle_info && <span>{loan.vehicle_info}</span>}
                    </div>
                  )}
                </button>
              ))
            )}
          </div>

          {/* Footer with count and keyboard hints */}
          {filteredLoans.length > 0 && (
            <div className="px-4 py-2 border-t border-border bg-muted flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Showing {filteredLoans.length} of {loans.length} loans
              </span>
              <span className="text-xs text-muted-foreground">
                Use ↑↓ to navigate, Enter to select
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
