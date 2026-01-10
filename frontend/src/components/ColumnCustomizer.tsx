'use client';

import { useState, useEffect } from 'react';
import {
  COLUMN_DEFINITIONS,
  DEFAULT_VISIBLE_COLUMNS,
  type ColumnDefinition,
} from '@/types/amortization';

interface ColumnCustomizerProps {
  visibleColumns: Set<string>;
  onChange: (columns: Set<string>) => void;
}

export default function ColumnCustomizer({
  visibleColumns,
  onChange,
}: ColumnCustomizerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [tempColumns, setTempColumns] = useState<Set<string>>(visibleColumns);

  // Update temp columns when visibleColumns changes
  useEffect(() => {
    setTempColumns(new Set(visibleColumns));
  }, [visibleColumns]);

  // Close on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
        setTempColumns(new Set(visibleColumns)); // Reset to original
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, visibleColumns]);

  const handleToggleColumn = (columnKey: string) => {
    const newSet = new Set(tempColumns);
    if (newSet.has(columnKey)) {
      newSet.delete(columnKey);
    } else {
      newSet.add(columnKey);
    }
    setTempColumns(newSet);
  };

  const handleSelectAll = () => {
    setTempColumns(new Set(COLUMN_DEFINITIONS.map((col) => col.key)));
  };

  const handleDeselectAll = () => {
    setTempColumns(new Set());
  };

  const handleResetToDefaults = () => {
    setTempColumns(new Set(DEFAULT_VISIBLE_COLUMNS));
  };

  const handleApply = () => {
    onChange(new Set(tempColumns));
    setIsOpen(false);
  };

  const handleCancel = () => {
    setTempColumns(new Set(visibleColumns));
    setIsOpen(false);
  };

  return (
    <>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-card-foreground bg-card border border-input rounded-lg hover:bg-muted transition-colors"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
          />
        </svg>
        Customize Columns
        <span className="px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-200 rounded-full">
          {visibleColumns.size}
        </span>
      </button>

      {/* Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          {/* Overlay */}
          <div
            className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
            onClick={handleCancel}
          />

          {/* Modal Content */}
          <div className="flex min-h-full items-center justify-center p-4">
            <div className="relative bg-card rounded-lg shadow-xl max-w-2xl w-full">
              {/* Header */}
              <div className="px-6 py-4 border-b border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-foreground">
                      Customize Columns
                    </h3>
                    <p className="text-sm text-muted-foreground mt-1">
                      Select which columns to display in the table
                    </p>
                  </div>
                  <button
                    onClick={handleCancel}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <svg
                      className="w-6 h-6"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  </button>
                </div>
              </div>

              {/* Body */}
              <div className="px-6 py-4 max-h-96 overflow-y-auto">
                {/* Quick Actions */}
                <div className="flex gap-2 mb-4 pb-4 border-b border-border">
                  <button
                    onClick={handleSelectAll}
                    className="px-3 py-1.5 text-xs font-medium text-blue-700 dark:text-blue-200 bg-blue-50 dark:bg-blue-950 rounded hover:bg-blue-100 dark:hover:bg-blue-900"
                  >
                    Select All
                  </button>
                  <button
                    onClick={handleDeselectAll}
                    className="px-3 py-1.5 text-xs font-medium text-card-foreground bg-muted rounded hover:bg-muted/80"
                  >
                    Deselect All
                  </button>
                  <button
                    onClick={handleResetToDefaults}
                    className="px-3 py-1.5 text-xs font-medium text-card-foreground bg-muted rounded hover:bg-muted/80"
                  >
                    Reset to Defaults
                  </button>
                  <div className="flex-1" />
                  <span className="px-3 py-1.5 text-xs text-muted-foreground bg-muted rounded">
                    {tempColumns.size} of {COLUMN_DEFINITIONS.length} selected
                  </span>
                </div>

                {/* Column Grid */}
                <div className="grid grid-cols-2 gap-3">
                  {COLUMN_DEFINITIONS.map((col) => (
                    <label
                      key={col.key}
                      className="flex items-start gap-2 p-3 rounded-lg border border-border hover:bg-muted cursor-pointer transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={tempColumns.has(col.key)}
                        onChange={() => handleToggleColumn(col.key)}
                        className="mt-0.5 h-4 w-4 text-blue-600 border-input rounded focus:ring-blue-500"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-foreground">
                          {col.label}
                        </div>
                        {col.description && (
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {col.description}
                          </div>
                        )}
                      </div>
                    </label>
                  ))}
                </div>

                {/* Warning */}
                {tempColumns.size === 0 && (
                  <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                    <p className="text-xs text-yellow-800 dark:text-yellow-200">
                      ⚠️ At least one column should be selected to view data
                    </p>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-border flex gap-3">
                <button
                  onClick={handleCancel}
                  className="flex-1 px-4 py-2 text-sm font-medium text-card-foreground bg-card border border-input rounded-lg hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  onClick={handleApply}
                  className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
                >
                  Apply Changes
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
