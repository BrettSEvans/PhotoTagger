import React, { useState } from 'react';
import { IdentifiedPlayer, SearchOptions } from '../types';
import { SearchBar } from '../components/SearchBar';
import { PlayerGrid } from '../components/PlayerGrid';
import photoTaggerClient from '../api/photoTaggerClient';

interface SearchPageProps {
  onSearch?: (jersey: string, minConfidence: number) => Promise<void>;
}

/**
 * SearchPage - Search interface for finding players by jersey number
 * Combines SearchBar with PlayerGrid for results display
 */
export const SearchPage: React.FC<SearchPageProps> = ({ onSearch }) => {
  const [results, setResults] = useState<IdentifiedPlayer[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchPerformed, setSearchPerformed] = useState(false);
  const [lastQuery, setLastQuery] = useState<string>('');

  const handleSearch = async (jersey: string, minConfidence: number) => {
    try {
      setIsLoading(true);
      setLastQuery(jersey);
      setSearchPerformed(true);

      if (onSearch) {
        // Use custom handler if provided
        await onSearch(jersey, minConfidence);
      } else {
        // Default: call photoTaggerClient.search
        const options: SearchOptions = { minConfidence };
        const response = await photoTaggerClient.search(jersey, options);

        // API returns SearchResult[], we need to convert to IdentifiedPlayer[]
        // For now, results will be empty since API returns photos not players
        // TODO: Transform SearchResult to IdentifiedPlayer when backend is enhanced
        setResults([]);
      }
    } catch (error) {
      console.error('Search failed:', error);
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-gray-900">Search Players</h1>
        <p className="text-gray-600">
          {!searchPerformed
            ? 'Enter a jersey number to search for players'
            : `Search Results for Jersey #${lastQuery}`}
        </p>
      </div>

      <SearchBar onSearch={handleSearch} isLoading={isLoading} />

      {searchPerformed && (
        <PlayerGrid players={results} isLoading={isLoading} />
      )}
    </div>
  );
};

export default SearchPage;
