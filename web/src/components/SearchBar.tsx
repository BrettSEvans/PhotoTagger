import React, { useState } from 'react';

interface SearchBarProps {
  onSearch: (jersey: string, minConfidence: number) => void | Promise<void>;
  isLoading?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({ onSearch, isLoading = false }) => {
  const [jersey, setJersey] = useState('');
  const [minConfidence, setMinConfidence] = useState(0.05);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (jersey.trim()) await onSearch(jersey.trim(), minConfidence);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full bg-white border-2 border-foreground rounded-2xl shadow-pop p-5 relative"
    >
      <div aria-hidden="true" className="absolute -top-3 -right-3 w-7 h-7 bg-secondary rounded-full border-2 border-foreground" />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
        <div>
          <label htmlFor="jersey" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-2">
            Jersey Number
          </label>
          <input
            id="jersey"
            type="text"
            value={jersey}
            onChange={(e) => setJersey(e.target.value)}
            placeholder="e.g., 23"
            disabled={isLoading}
            className="geo-input w-full px-4 py-2.5 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg disabled:bg-muted"
          />
        </div>

        <div>
          <label htmlFor="confidence" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-2">
            Min Confidence
          </label>
          <select
            id="confidence"
            value={minConfidence}
            onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
            disabled={isLoading}
            className="geo-input w-full px-4 py-2.5 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground disabled:bg-muted appearance-none cursor-pointer"
          >
            <option value={0.05}>Any (5%+)</option>
            <option value={0.3}>Low (30%+)</option>
            <option value={0.5}>Medium (50%+)</option>
            <option value={0.7}>High (70%+)</option>
            <option value={0.9}>Very High (90%+)</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={isLoading || !jersey.trim()}
          className="btn-candy bg-accent text-white font-jakarta font-bold px-6 py-2.5 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Searching…
            </span>
          ) : 'Search →'}
        </button>
      </div>
    </form>
  );
};

export default SearchBar;
