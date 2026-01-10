'use client';

import { useState, useEffect } from 'react';
import { settingsAPI } from '@/lib/api';

interface SettingsFormProps {
  settingKey: string;
  label: string;
  description: string;
  placeholder: string;
  type: 'sheet' | 'folder';
}

export function SettingsForm({ settingKey, label, description, placeholder, type }: SettingsFormProps) {
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [initialValue, setInitialValue] = useState('');

  // Load current setting
  useEffect(() => {
    const loadSetting = async () => {
      try {
        const setting = await settingsAPI.get(settingKey);
        setValue(setting.value);
        setInitialValue(setting.value);
      } catch (err) {
        console.error('Failed to load setting:', err);
        setError('Failed to load current setting value');
      } finally {
        setLoadingInitial(false);
      }
    };
    loadSetting();
  }, [settingKey]);

  const handleSave = async () => {
    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      await settingsAPI.update(settingKey, value, type);
      await settingsAPI.clearCache();
      setInitialValue(value);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to update setting';
      // Extract detail from error message if it's a JSON response
      try {
        const errorJson = JSON.parse(errorMessage);
        setError(errorJson.detail || errorMessage);
      } catch {
        setError(errorMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  const hasChanges = value !== initialValue;

  if (loadingInitial) {
    return (
      <div className="space-y-4">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/4 mb-2"></div>
          <div className="h-10 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          {label}
        </label>
        <p className="text-sm text-gray-600 mb-3">{description}</p>
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          disabled={loading}
        />
        <p className="mt-2 text-xs text-gray-500">
          Accepts full Google URL or direct ID
        </p>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
          {error}
        </div>
      )}

      {success && (
        <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
          Settings updated successfully! Changes will take effect on the next import operation.
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={loading || !hasChanges || !value.trim()}
        className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? 'Validating and saving...' : 'Save Changes'}
      </button>

      {hasChanges && !loading && (
        <p className="text-xs text-gray-500">
          You have unsaved changes
        </p>
      )}
    </div>
  );
}
