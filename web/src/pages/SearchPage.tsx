import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from '../components/LoadingSpinner';
import type { PlayerPhotoItem, RosterSearchResult } from '../types/index';

interface ClusterWithAssignment {
  id: number;
  face_count: number;
  photo_count: number;
  thumbnail_face_id: number | null;
  created_at: string;
  player_name?: string;
  jersey_number?: string;
  roster_entry_id?: number | null;
}

export const SearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query,           setQuery]           = useState('');
  const [rosterMatches,   setRosterMatches]   = useState<RosterSearchResult[]>([]);
  const [selectedPlayer,  setSelectedPlayer]  = useState<RosterSearchResult | null>(null);
  const [cluster,         setCluster]         = useState<ClusterWithAssignment | null>(null);
  const [photos,          setPhotos]          = useState<PlayerPhotoItem[]>([]);
  const [modalPhoto,      setModalPhoto]      = useState<PlayerPhotoItem | null>(null);
  const [lens,            setLens]            = useState<{ photo: PlayerPhotoItem; x: number; y: number } | null>(null);
  const [isSearching,     setIsSearching]     = useState(false);
  const [isLoadingPhotos, setIsLoadingPhotos] = useState(false);
  const [removingFaces,   setRemovingFaces]   = useState<Set<number>>(new Set());
  const [error,           setError]           = useState<string | null>(null);

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Debounced roster search ──────────────────────────────────────────────
  const handleQueryChange = useCallback((q: string) => {
    setQuery(q);
    if (q.trim()) {
      setSearchParams({ q });
    } else {
      setSearchParams({});
    }
    setSelectedPlayer(null);
    setPhotos([]);
    setCluster(null);
    setRosterMatches([]);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!q.trim()) return;

    setIsSearching(true);
    searchTimer.current = setTimeout(async () => {
      try {
        const results = await photoTaggerClient.searchRoster(q);
        setRosterMatches(results);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Search failed');
      } finally {
        setIsSearching(false);
      }
    }, 200);
  }, [setSearchParams]);

  // Restore search query from URL on mount
  useEffect(() => {
    const q = searchParams.get('q');
    if (q) {
      setQuery(q);
    }
  }, []);

  // ── Select player → load their photos ───────────────────────────────────
  const selectPlayer = useCallback(async (player: RosterSearchResult) => {
    setSelectedPlayer(player);
    setRosterMatches([]);
    setQuery(player.player_name);
    setPhotos([]);
    setCluster(null);
    setError(null);
    setIsLoadingPhotos(true);

    try {
      // Prefer the stable roster entry link; fall back to older clusters by name/jersey.
      const playersData = await photoTaggerClient.getPlayers();
      const allClusters = playersData.players as ClusterWithAssignment[];
      const matched = allClusters.find(c => c.roster_entry_id === player.id)
        ?? allClusters.find(c => c.player_name === player.player_name)
        ?? allClusters.find(c => c.jersey_number === player.jersey_number)
        ?? null;
      setCluster(matched);

      let merged: PlayerPhotoItem[] = [];

      if (matched) {
        const clusterData = await photoTaggerClient.getPlayerPhotos(matched.id);
        merged = clusterData.photos;
      }

      // Supplement with OCR-tagged photos by jersey number
      try {
        const ocrData = await photoTaggerClient.search(player.jersey_number);
        for (const result of ocrData.results) {
          if (!merged.some(p => p.id === result.id)) {
            merged.push({
              id: result.id,
              filename: result.file_path.split('/').pop() || result.file_path,
              path: result.file_path,
              added_at: '',
              face_id: 0,
              face_bbox: [0, 0, 0, 0],
              face_confidence: result.confidence,
            });
          }
        }
      } catch {
        // OCR search is best-effort
      }

      setPhotos(merged);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load photos');
    } finally {
      setIsLoadingPhotos(false);
    }
  }, []);

  // ── Remove face assignment from selected player ─────────────────────────
  const removeFromPlayer = useCallback(async (photo: PlayerPhotoItem) => {
    if (photo.face_id === 0) return;
    const playerName = selectedPlayer?.player_name ?? 'this player';
    const confirmed = window.confirm(`Remove ${photo.filename} from ${playerName}?`);
    if (!confirmed) return;

    setRemovingFaces(prev => new Set(prev).add(photo.face_id));
    setError(null);
    try {
      await photoTaggerClient.deassignFaces([photo.face_id]);
      setPhotos(prev => prev.filter(p => p.face_id !== photo.face_id));
      if (modalPhoto?.face_id === photo.face_id) setModalPhoto(null);
      if (lens?.photo.face_id === photo.face_id) setLens(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove photo from player');
    } finally {
      setRemovingFaces(prev => {
        const next = new Set(prev);
        next.delete(photo.face_id);
        return next;
      });
    }
  }, [lens, modalPhoto, selectedPlayer]);

  const clearSearch = () => {
    setQuery('');
    setRosterMatches([]);
    setSelectedPlayer(null);
    setPhotos([]);
    setCluster(null);
    setRemovingFaces(new Set());
    setError(null);
  };

  return (
    <div className="w-full max-w-7xl mx-auto py-4 space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-outfit text-4xl font-extrabold text-foreground">Search</h1>
        <p className="mt-2 font-jakarta text-muted-fg">Find all photos of a player by name or jersey number</p>
      </div>

      {error && (
        <div role="alert" className="bg-white border-2 border-secondary rounded-xl shadow-pop-pink p-3 flex items-center justify-between">
          <p className="font-jakarta text-sm text-foreground">⚠️ {error}</p>
          <button onClick={() => setError(null)} className="font-jakarta text-xs text-muted-fg hover:text-foreground ml-4">×</button>
        </div>
      )}

      {/* Search input */}
      <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop overflow-visible">
        <div className="px-5 py-4">
          <div className="relative">
            <div className="flex items-center gap-3 px-4 py-3 bg-muted/30 border-2 border-frame rounded-xl focus-within:border-foreground transition-colors">
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" className="text-muted-fg flex-shrink-0">
                <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
              </svg>
              <input
                type="text"
                value={query}
                onChange={e => handleQueryChange(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Escape') clearSearch();
                  if (e.key === 'Enter' && rosterMatches.length > 0) selectPlayer(rosterMatches[0]);
                }}
                placeholder="Type player name or jersey number…"
                className="flex-1 bg-transparent border-0 font-jakarta text-base text-foreground placeholder:text-muted-fg outline-none"
                autoFocus
              />
              {isSearching && (
                <span className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin block flex-shrink-0" />
              )}
              {query && !isSearching && (
                <button onClick={clearSearch} className="font-jakarta text-xs text-muted-fg hover:text-foreground px-2 py-0.5 rounded border border-frame hover:border-foreground transition-colors flex-shrink-0">
                  Clear
                </button>
              )}
            </div>

            {/* Roster match dropdown */}
            {rosterMatches.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white border-2 border-foreground rounded-xl shadow-pop-lg overflow-hidden divide-y divide-frame z-10">
                {rosterMatches.map((result, i) => (
                  <button
                    key={result.id}
                    onClick={() => selectPlayer(result)}
                    className={`w-full text-left px-4 py-2.5 flex items-center gap-3 hover:bg-accent/5 transition-colors ${i === 0 ? 'bg-muted/20' : ''}`}
                  >
                    <span className="w-9 h-9 bg-accent rounded-lg border-2 border-foreground shadow-pop-sm flex items-center justify-center flex-shrink-0">
                      <span className="font-outfit font-extrabold text-white text-xs leading-none">#{result.jersey_number}</span>
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-outfit font-bold text-foreground text-sm">{result.player_name}</p>
                      <p className="font-jakarta text-xs text-muted-fg">{result.team_name}</p>
                    </div>
                    {i === 0 && (
                      <span className="font-jakarta text-xs text-muted-fg bg-muted px-2 py-0.5 rounded border border-frame whitespace-nowrap">↵ Enter</span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {/* No results */}
            {query && !isSearching && rosterMatches.length === 0 && !selectedPlayer && (
              <p className="mt-2 font-jakarta text-xs text-muted-fg text-center py-2">
                No player found for "{query}" — add them on the Roster tab
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Player header */}
      {selectedPlayer && (
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop px-5 py-4 flex items-center gap-4">
          {cluster?.thumbnail_face_id && (
            <div className="w-14 h-14 rounded-full overflow-hidden border-2 border-foreground shadow-pop-sm flex-shrink-0">
              <img src={photoTaggerClient.getFaceCropUrl(cluster.thumbnail_face_id)} alt="" className="w-full h-full object-cover" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p className="font-outfit font-extrabold text-foreground text-lg leading-tight">{selectedPlayer.player_name}</p>
            <p className="font-jakarta text-sm text-muted-fg">
              #{selectedPlayer.jersey_number} · {selectedPlayer.team_name}
              {!isLoadingPhotos && ` · ${photos.length} photo${photos.length !== 1 ? 's' : ''}`}
            </p>
          </div>
          {!cluster && !isLoadingPhotos && (
            <span className="font-jakarta text-xs text-muted-fg bg-muted px-3 py-1.5 rounded-full border border-frame">
              No face cluster assigned yet
            </span>
          )}
        </div>
      )}

      {/* Photo grid */}
      {selectedPlayer && (
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop overflow-hidden">
          <div className="px-4 py-3 border-b-2 border-foreground flex items-center justify-between">
            <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg">
              Photos · {photos.length} found
            </p>
            {cluster && (
              <span className="font-jakarta text-xs text-quaternary font-bold bg-quaternary/10 px-2 py-1 rounded-full border border-quaternary">
                Face-matched
              </span>
            )}
          </div>

          {isLoadingPhotos ? (
            <div className="flex justify-center py-16"><LoadingSpinner message="Loading photos…" /></div>
          ) : photos.length === 0 ? (
            <div className="py-16 text-center">
              <svg width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="text-muted-fg mx-auto mb-3">
                <rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 7l-2-4H10L8 7" /><circle cx="12" cy="14" r="3" />
              </svg>
              <p className="font-outfit font-bold text-foreground">No photos found</p>
              <p className="font-jakarta text-xs text-muted-fg mt-1">
                {cluster ? "No photos in this player's cluster" : 'Assign a face cluster to this player in Cleanup Workspace first'}
              </p>
            </div>
          ) : (
            <div className="p-3 grid grid-cols-4 sm:grid-cols-6 md:grid-cols-7 lg:grid-cols-8 xl:grid-cols-10 gap-2">
              {photos.map(photo => {
                const src = photoTaggerClient.getPhotoUrl(photo.id);
                const hasFace = photo.face_id !== 0;
                const isRemoving = removingFaces.has(photo.face_id);
                return (
                  <div
                    key={photo.id}
                    onMouseEnter={e => setLens({ photo, x: e.clientX, y: e.clientY })}
                    onMouseMove={e => setLens({ photo, x: e.clientX, y: e.clientY })}
                    onMouseLeave={() => setLens(null)}
                    className="relative aspect-square rounded-lg overflow-hidden border-2 border-accent shadow-pop-sm"
                  >
                    <img
                      src={src}
                      alt={photo.filename}
                      className="w-full h-full object-cover"
                      onError={e => { e.currentTarget.style.display = 'none'; }}
                    />

                    {/* Enlarge button */}
                    <button
                      onClick={() => setModalPhoto(photo)}
                      aria-label="View full size"
                      className="absolute top-1 right-1 w-5 h-5 rounded bg-white/80 border border-frame flex items-center justify-center hover:bg-white transition-colors"
                    >
                      <svg width="8" height="8" fill="none" stroke="#1E293B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 10 10">
                        <path d="M1 4V1h3M6 1h3v3M9 6v3H6M4 9H1V6" />
                      </svg>
                    </button>

                    {hasFace && (
                      <button
                        onClick={e => { e.stopPropagation(); removeFromPlayer(photo); }}
                        disabled={isRemoving}
                        aria-label={`Remove ${photo.filename} from ${selectedPlayer.player_name}`}
                        title="Remove this photo from the current player"
                        className="absolute bottom-1 left-1 right-1 min-h-6 rounded bg-white/90 border border-frame px-1.5 font-jakarta text-[10px] font-bold text-foreground hover:border-secondary hover:text-secondary disabled:opacity-60 transition-colors"
                      >
                        {isRemoving ? 'Removing…' : 'Remove'}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Initial empty state */}
      {!selectedPlayer && !query && (
        <div className="bg-white border-2 border-frame rounded-2xl flex items-center justify-center p-20 text-center">
          <div>
            <svg width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="text-muted-fg mx-auto mb-4">
              <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
            </svg>
            <p className="font-outfit font-bold text-foreground">Search for a player</p>
            <p className="font-jakarta text-xs text-muted-fg mt-1 max-w-xs">
              Type a name or jersey number above to see all their tagged photos
            </p>
          </div>
        </div>
      )}

      {/* ── Hover-zoom lens ──────────────────────────────────────────────────── */}
      {lens && !modalPhoto && (() => {
        const W = 300;
        const left = Math.min(lens.x + 24, window.innerWidth  - W - 16);
        const top  = Math.min(lens.y + 24, window.innerHeight - W - 48);
        return (
          <div className="fixed z-40 pointer-events-none" style={{ left, top, width: W }}>
            <div className="relative inline-block rounded-xl overflow-hidden border-2 border-foreground shadow-pop-lg bg-white">
              <img src={photoTaggerClient.getPhotoUrl(lens.photo.id)} alt="" className="block" style={{ width: W }} />
              <div className="absolute bottom-0 left-0 right-0 bg-foreground/80 px-2 py-1">
                <span className="font-jakarta text-white truncate" style={{ fontSize: '10px' }}>{lens.photo.filename}</span>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── Full-size modal ──────────────────────────────────────────────────── */}
      {modalPhoto && (
        <div
          className="fixed inset-0 z-50 bg-foreground/80 flex items-center justify-center p-4"
          onClick={() => setModalPhoto(null)}
        >
          <div className="relative" onClick={e => e.stopPropagation()}>
            <button
              onClick={() => setModalPhoto(null)}
              className="absolute -top-10 right-0 font-jakarta text-white font-bold text-sm flex items-center gap-1 hover:text-tertiary transition-colors"
            >
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 14 14"><path d="M1 1l12 12M13 1L1 13"/></svg>
              Close
            </button>

            <div className="relative inline-block rounded-xl overflow-hidden border-2 border-white shadow-pop-lg">
              <img
                src={photoTaggerClient.getPhotoUrl(modalPhoto.id)}
                alt={modalPhoto.filename}
                className="block max-w-[90vw] max-h-[85vh]"
                style={{ display: 'block' }}
              />
            </div>

            <div className="mt-2 flex items-center justify-between px-1">
              <p className="font-jakarta text-white text-xs">{modalPhoto.filename}</p>
              {modalPhoto.face_id !== 0 && (
                <button
                  onClick={() => removeFromPlayer(modalPhoto)}
                  disabled={removingFaces.has(modalPhoto.face_id)}
                  className="font-jakarta text-white text-xs border border-white/40 rounded-full px-3 py-1 hover:border-white hover:bg-white/10 disabled:opacity-60 transition-colors"
                >
                  {removingFaces.has(modalPhoto.face_id) ? 'Removing…' : 'Remove from player'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SearchPage;
