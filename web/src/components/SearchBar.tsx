import React, { useState } from 'react';

interface SearchBarProps {
  onSearch: (jersey: string, minConfidence: number) => void | Promise<void>;
  isLoading?: boolean;
}

/**
 * SearchBar - Jersey number search form with confidence threshold
 * Allows users to search for photos with specific jersey numbers
 */
export const SearchBar: React.FC<SearchBarProps> = ({
  onSearch,
  isLoading = false,
}) => {
  const [jersey, setJersey] = useState('');
  const [minConfidence, setMinConfidence] = useState(0.7);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (jersey.trim()) {
      await onSearch(jersey.trim(), minConfidence);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full bg-white border border-gray-200 rounded-lg shadow-sm p-4"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
        <div>
          <label htmlFor="jersey" className="block text-sm font-medium text-gray-700 mb-1">
            Jersey Number
          </label>
          <input
            id="jersey"
            type="text"
            value={jersey}
            onChange={(e) => setJersey(e.target.value)}
            placeholder="e.g., 23"
            disabled={isLoading}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:text-gray-500"
          />
        </div>

        <div>
          <label htmlFor="confidence" className="block text-sm font-medium text-gray-700 mb-1">
            Min Confidence
          </label>
          <select
            id="confidence"
            value={minConfidence}
            onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
            disabled={isLoading}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:text-gray-500"
          >
            <option value={0.5}>50%</option>
            <option value={0.6}>60%</option>
            <option value={0.7}>70%</option>
            <option value={0.8}>80%</option>
            <option value={0.9}>90%</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={isLoading || !jersey.trim()}
          className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium rounded-md transition-colors"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Searching...
            </span>
          ) : (
            'Search'
          )}
        </button>
      </div>
    </form>
  );
};

export default SearchBar;
