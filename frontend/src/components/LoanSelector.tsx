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
  const dropdownRef = useRef<HTMLDivElement>(null);

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

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
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

  const handleClear = () => {
    onChange('');
    setSearchTerm('');
    setIsOpen(false);
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
          disabled={loading}
          className={`w-full px-4 py-2 text-left border border-gray-300 rounded-lg bg-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors ${
            loading ? 'opacity-50 cursor-not-allowed' : 'hover:border-gray-400'
          }`}
        >
          <span className={value ? 'text-gray-900' : 'text-gray-500'}>
            {loading ? 'Loading loans...' : displayText}
          </span>
        </button>

        {/* Clear button */}
        {value && !loading && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-10 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 p-1"
            aria-label="Clear selection"
          >
            ✕
          </button>
        )}

        {/* Dropdown arrow */}
        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
          <svg
            className={`w-5 h-5 text-gray-400 transition-transform ${
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
        <div className="absolute z-50 w-full mt-2 bg-white border border-gray-300 rounded-lg shadow-lg max-h-96 flex flex-col">
          {/* Search input */}
          <div className="p-3 border-b border-gray-200">
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search loans..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              autoFocus
            />
          </div>

          {/* Loan list */}
          <div className="overflow-y-auto">
            {filteredLoans.length === 0 ? (
              <div className="px-4 py-8 text-center text-gray-500 text-sm">
                No loans found
              </div>
            ) : (
              filteredLoans.map((loan) => (
                <button
                  key={loan.loan_id}
                  type="button"
                  onClick={() => handleSelect(loan.loan_id)}
                  className={`w-full px-4 py-3 text-left hover:bg-blue-50 transition-colors border-b border-gray-100 last:border-b-0 ${
                    loan.loan_id === value ? 'bg-blue-50' : ''
                  }`}
                >
                  <div className="font-medium text-gray-900">
                    {loan.loan_id}
                  </div>
                  {(loan.customer_name || loan.vehicle_info) && (
                    <div className="text-sm text-gray-600 mt-1">
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

          {/* Footer with count */}
          {filteredLoans.length > 0 && (
            <div className="px-4 py-2 border-t border-gray-200 bg-gray-50 text-xs text-gray-600">
              Showing {filteredLoans.length} of {loans.length} loans
            </div>
          )}
        </div>
      )}
    </div>
  );
}
