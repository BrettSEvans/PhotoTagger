import React, { useState, useRef, useCallback, useEffect } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import type { RosterSearchResult, MatchSimilarResponse } from '../types/index';

export interface AssignedInfo {
  playerName: string;
  jerseyNumber: string;
  rosterEntryId: number;
  /** Result of the post-assign similarity scan (auto-tagged + suggested clusters). */
  matches?: MatchSimilarResponse;
}

interface AssignPlayerPanelProps {
  /** Cluster to assign to a roster player. */
  clusterId: number;
  /** Called after a successful assign + similarity scan. */
  onAssigned: (info: AssignedInfo) => void;
  autoFocus?: boolean;
  placeholder?: string;
}

/**
 * AssignPlayerPanel — the single, reusable "tag this player" workflow.
 *
 * Encapsulates roster search → assign cluster → post-assign similarity scan
 * (the same backend pipeline used by the Review tab) so every surface that
 * tags a player shares one implementation. After assigning, the cluster's
 * face is used to auto-identify the player across other photos/clusters.
 */
export const AssignPlayerPanel: React.FC<AssignPlayerPanelProps> = ({
  clusterId,
  onAssigned,
  autoFocus = false,
  placeholder = 'Search roster by name or number…',
}) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<RosterSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isAssigning, setIsAssigning] = useState(false);
  const [isMatching, setIsMatching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current); };
  }, [autoFocus]);

  const handleSearchChange = useCallback((q: string) => {
    setQuery(q);
    setError(null);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!q.trim()) { setResults([]); return; }
    searchTimer.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        setResults(await photoTaggerClient.searchRoster(q));
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Roster search failed');
      } finally {
        setIsSearching(false);
      }
    }, 200);
  }, []);

  const handleAssign = async (result: RosterSearchResult) => {
    setIsAssigning(true);
    setError(null);
    try {
      // Assign the whole cluster to the chosen roster player.
      await photoTaggerClient.assignCluster(
        clusterId,
        result.player_name,
        result.jersey_number,
        result.id,
      );

      // Best-effort: use this face to find the same player in other clusters.
      let matches: MatchSimilarResponse | undefined;
      setIsMatching(true);
      try {
        matches = await photoTaggerClient.matchSimilarClusters(clusterId);
      } catch {
        // Similarity scan is best-effort — don't block the assignment on it.
      } finally {
        setIsMatching(false);
      }

      setQuery('');
      setResults([]);
      onAssigned({
        playerName: result.player_name,
        jerseyNumber: result.jersey_number,
        rosterEntryId: result.id,
        matches,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Assignment failed');
    } finally {
      setIsAssigning(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && results.length > 0 && !isAssigning) handleAssign(results[0]);
    if (e.key === 'Escape') { setQuery(''); setResults([]); }
  };

  const busy = isAssigning || isMatching;

  return (
    <div className="space-y-2">
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => handleSearchChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={busy}
          className="w-full px-4 py-2 border-2 border-frame rounded-lg font-jakarta text-sm focus:outline-none focus:border-accent disabled:opacity-50"
        />
        {isSearching && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        )}
      </div>

      {results.length > 0 && (
        <ul className="border-2 border-frame rounded-lg divide-y divide-frame max-h-60 overflow-y-auto bg-white">
          {results.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => handleAssign(r)}
                disabled={busy}
                className="w-full text-left px-3 py-2 hover:bg-quaternary/10 disabled:opacity-50 flex items-center justify-between gap-2"
              >
                <span className="font-jakarta text-sm font-semibold text-foreground truncate">
                  {r.player_name}
                  <span className="ml-2 text-accent font-bold">#{r.jersey_number}</span>
                </span>
                <span className="font-jakarta text-xs text-muted-fg truncate">{r.team_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {busy && (
        <p role="status" className="font-jakarta text-xs text-muted-fg flex items-center gap-2">
          <span className="w-3 h-3 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          {isMatching ? 'Finding this player in other photos…' : 'Assigning…'}
        </p>
      )}

      {error && (
        <p role="alert" className="font-jakarta text-xs text-secondary">⚠️ {error}</p>
      )}
    </div>
  );
};

export default AssignPlayerPanel;
