import React, { useState } from 'react';
import type { SearchOptions } from '../types';
import { SearchBar } from '../components/SearchBar';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from '../components/LoadingSpinner';
import type { SearchResult } from '../types';

export const SearchPage: React.FC = () => {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchPerformed, setSearchPerformed] = useState(false);
  const [lastQuery, setLastQuery] = useState('');

  const handleSearch = async (jersey: string, minConfidence: number) => {
    setIsLoading(true);
    setLastQuery(jersey);
    setSearchPerformed(true);
    try {
      const options: SearchOptions = { minConfidence };
      const response = await photoTaggerClient.search(jersey, options);
      setResults(response.results);
    } catch (error) {
      console.error('Search failed:', error);
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full space-y-6">
      <div>
        <h1 className="font-outfit text-4xl font-extrabold text-foreground">
          {!searchPerformed ? 'Search by Jersey' : `Jersey #${lastQuery}`}
        </h1>
        <p className="mt-2 font-jakarta text-muted-fg">
          {!searchPerformed
            ? 'Find photos by jersey number across both rosters'
            : `${results.length} photo${results.length !== 1 ? 's' : ''} found`}
        </p>
      </div>

      <SearchBar onSearch={handleSearch} isLoading={isLoading} />

      {isLoading && (
        <div className="flex justify-center py-12">
          <LoadingSpinner message="Searching photos…" />
        </div>
      )}

      {searchPerformed && !isLoading && results.length === 0 && (
        <div role="status" className="bg-white border-2 border-foreground rounded-2xl shadow-pop p-10 text-center relative overflow-hidden">
          <div aria-hidden="true" className="absolute top-3 right-3 w-6 h-6 bg-tertiary rotate-45 border-2 border-foreground opacity-60" />
          <p className="font-outfit text-2xl font-bold text-foreground mb-2">No results</p>
          <p className="font-jakarta text-muted-fg">
            Jersey #{lastQuery} wasn't detected in any photos yet.<br/>
            Try running OCR from the Upload page first.
          </p>
        </div>
      )}

      {results.length > 0 && !isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {results.map((result) => (
            <div
              key={result.id}
              className="sticker-card bg-white border-2 border-foreground rounded-2xl shadow-pop overflow-hidden"
            >
              {/* Photo thumbnail */}
              <div className="aspect-video bg-muted overflow-hidden">
                <img
                  src={`http://127.0.0.1:5001/api/image/${result.id}`}
                  alt={result.file_path}
                  className="w-full h-full object-cover"
                  onError={(e) => { e.currentTarget.style.display = 'none'; }}
                />
              </div>

              <div className="p-4">
                {/* Jersey number badge */}
                <div className="flex items-start gap-3">
                  <div className="w-12 h-12 flex-shrink-0 bg-accent rounded-xl border-2 border-foreground shadow-pop-sm flex items-center justify-center">
                    <span className="font-outfit font-extrabold text-white text-lg leading-none">
                      #{result.jersey_number}
                    </span>
                  </div>
                  <div className="min-w-0">
                    {result.player_name && (
                      <p className="font-outfit font-bold text-foreground text-sm truncate">{result.player_name}</p>
                    )}
                    <p className="font-jakarta text-xs text-muted-fg truncate">{result.file_path.split('/').pop()}</p>
                    {/* Confidence bar */}
                    <div className="mt-2 flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-quaternary rounded-full"
                          style={{ width: `${Math.min(result.confidence * 100, 100)}%` }}
                        />
                      </div>
                      <span className="font-jakarta text-xs text-muted-fg whitespace-nowrap">
                        {Math.round(result.confidence * 100)}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SearchPage;
