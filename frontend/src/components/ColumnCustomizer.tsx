'use client';

import { useMemo } from 'react';
import {
  COLUMN_DEFINITIONS,
  COLUMN_CATEGORIES,
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
  const categorizedColumns = useMemo(() => {
    const result: Record<string, ColumnDefinition[]> = {};
    COLUMN_DEFINITIONS.forEach((col) => {
      if (!result[col.category]) {
        result[col.category] = [];
      }
      result[col.category].push(col);
    });
    return result;
  }, []);

  const handleToggleColumn = (columnKey: string) => {
    const newSet = new Set(visibleColumns);
    if (newSet.has(columnKey)) {
      newSet.delete(columnKey);
    } else {
      newSet.add(columnKey);
    }
    onChange(newSet);
  };

  const handleToggleCategory = (category: string) => {
    const categoryColumns = categorizedColumns[category];
    const allSelected = categoryColumns.every((col) =>
      visibleColumns.has(col.key)
    );

    const newSet = new Set(visibleColumns);
    if (allSelected) {
      // Deselect all in category
      categoryColumns.forEach((col) => newSet.delete(col.key));
    } else {
      // Select all in category
      categoryColumns.forEach((col) => newSet.add(col.key));
    }
    onChange(newSet);
  };

  const handleResetToDefaults = () => {
    onChange(new Set(DEFAULT_VISIBLE_COLUMNS));
  };

  const getCategoryStats = (category: string) => {
    const categoryColumns = categorizedColumns[category];
    const selectedCount = categoryColumns.filter((col) =>
      visibleColumns.has(col.key)
    ).length;
    return { selected: selectedCount, total: categoryColumns.length };
  };

  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">
            Column Selection
          </h3>
          <p className="text-xs text-gray-600 mt-1">
            {visibleColumns.size} of {COLUMN_DEFINITIONS.length} columns
            selected
          </p>
        </div>
        <button
          type="button"
          onClick={handleResetToDefaults}
          className="px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 rounded hover:bg-blue-100 transition-colors"
        >
          Reset to Defaults
        </button>
      </div>

      {/* Categories */}
      <div className="space-y-3">
        {COLUMN_CATEGORIES.map((category) => {
          const stats = getCategoryStats(category.id);
          const allSelected = stats.selected === stats.total;

          return (
            <div
              key={category.id}
              className="border border-gray-200 rounded-lg bg-white"
            >
              {/* Category header */}
              <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50">
                <div className="flex items-center gap-2">
                  <span className="text-base">{category.icon}</span>
                  <span className="text-sm font-medium text-gray-900">
                    {category.label}
                  </span>
                  <span className="text-xs text-gray-500">
                    ({stats.selected}/{stats.total})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => handleToggleCategory(category.id)}
                  className="text-xs font-medium text-blue-700 hover:text-blue-800 transition-colors"
                >
                  {allSelected ? 'Deselect All' : 'Select All'}
                </button>
              </div>

              {/* Category columns */}
              <div className="p-3 space-y-2">
                {categorizedColumns[category.id]?.map((col) => (
                  <label
                    key={col.key}
                    className="flex items-start gap-3 cursor-pointer hover:bg-gray-50 p-2 rounded transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={visibleColumns.has(col.key)}
                      onChange={() => handleToggleColumn(col.key)}
                      className="mt-0.5 h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900">
                        {col.label}
                      </div>
                      {col.description && (
                        <div className="text-xs text-gray-500 mt-0.5">
                          {col.description}
                        </div>
                      )}
                    </div>
                  </label>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Warning if no columns selected */}
      {visibleColumns.size === 0 && (
        <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
          <p className="text-xs text-yellow-800">
            ⚠️ At least one column should be selected to view data
          </p>
        </div>
      )}
    </div>
  );
}
