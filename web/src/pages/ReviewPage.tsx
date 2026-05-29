import React, { useState, useEffect, useRef, useCallback } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from '../components/LoadingSpinner';
import type { PlayerCluster, PlayerPhotoItem, RosterSearchResult } from '../types/index';

interface ClusterWithAssignment extends PlayerCluster {
  player_name?: string;
  jersey_number?: string;
}

interface ImgDim { w: number; h: number }

// Returns % positioning for a face bbox overlay, given the image's natural dimensions.
// Works with object-cover (percentage maps through the scale uniformly).
function bboxStyle(bbox: [number, number, number, number], dim: ImgDim) {
  return {
    left:   `${(bbox[0] / dim.w) * 100}%`,
    top:    `${(bbox[1] / dim.h) * 100}%`,
    width:  `${((bbox[2] - bbox[0]) / dim.w) * 100}%`,
    height: `${((bbox[3] - bbox[1]) / dim.h) * 100}%`,
  };
}

export const ReviewPage: React.FC = () => {
  // ── Cluster list ────────────────────────────────────────────────────────
  const [clusters,        setClusters]        = useState<ClusterWithAssignment[]>([]);
  const [selectedCluster, setSelectedCluster] = useState<ClusterWithAssignment | null>(null);
  const [clusterPhotos,   setClusterPhotos]   = useState<PlayerPhotoItem[]>([]);
  const [isLoadingList,   setIsLoadingList]   = useState(true);
  const [isLoadingPhotos, setIsLoadingPhotos] = useState(false);

  // ── Bulk selection ──────────────────────────────────────────────────────
  // Keyed by face_id; true = included in next assign, false = excluded
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // ── Image natural dims for bbox overlay ─────────────────────────────────
  const [imgDims, setImgDims] = useState<Map<number, ImgDim>>(new Map());

  // ── Full-size modal ─────────────────────────────────────────────────────
  const [modalPhoto,  setModalPhoto]  = useState<PlayerPhotoItem | null>(null);
  const [modalDim,    setModalDim]    = useState<ImgDim | null>(null);

  // ── Roster search ────────────────────────────────────────────────────────
  const [searchQuery,   setSearchQuery]   = useState('');
  const [searchResults, setSearchResults] = useState<RosterSearchResult[]>([]);
  const [isSearching,   setIsSearching]   = useState(false);
  const [assignSuccess, setAssignSuccess] = useState<string | null>(null);
  const [error,         setError]         = useState<string | null>(null);
  const [isAssigning,   setIsAssigning]   = useState(false);

  const searchRef   = useRef<HTMLInputElement>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Load clusters ────────────────────────────────────────────────────────
  useEffect(() => { loadClusters(); }, []);

  const loadClusters = async () => {
    setIsLoadingList(true);
    try {
      const data = await photoTaggerClient.getPlayers();
      setClusters(data.players as ClusterWithAssignment[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load clusters');
    } finally { setIsLoadingList(false); }
  };

  // ── Select cluster ───────────────────────────────────────────────────────
  const selectCluster = async (cluster: ClusterWithAssignment) => {
    setSelectedCluster(cluster);
    setClusterPhotos([]);
    setSelected(new Set());
    setImgDims(new Map());
    setSearchQuery('');
    setSearchResults([]);
    setAssignSuccess(null);
    setModalPhoto(null);
    setIsLoadingPhotos(true);
    setTimeout(() => searchRef.current?.focus(), 150);
    try {
      const data = await photoTaggerClient.getPlayerPhotos(cluster.id);
      setClusterPhotos(data.photos);
      // Default: all photos selected
      setSelected(new Set(data.photos.map(p => p.face_id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load photos');
    } finally { setIsLoadingPhotos(false); }
  };

  // ── Selection helpers ────────────────────────────────────────────────────
  const togglePhoto = (faceId: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(faceId) ? next.delete(faceId) : next.add(faceId);
      return next;
    });
  };
  const selectAll   = () => setSelected(new Set(clusterPhotos.map(p => p.face_id)));
  const deselectAll = () => setSelected(new Set());

  // ── Image load → capture natural dims ───────────────────────────────────
  const handleImgLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>, photoId: number) => {
    const img = e.currentTarget;
    setImgDims(prev => {
      const next = new Map(prev);
      next.set(photoId, { w: img.naturalWidth, h: img.naturalHeight });
      return next;
    });
  }, []);

  // ── Roster search (debounced) ────────────────────────────────────────────
  const handleSearchChange = useCallback((q: string) => {
    setSearchQuery(q);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!q.trim()) { setSearchResults([]); return; }
    searchTimer.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        const results = await photoTaggerClient.searchRoster(q);
        setSearchResults(results);
      } finally { setIsSearching(false); }
    }, 200);
  }, []);

  // ── Assign selected photos ───────────────────────────────────────────────
  const handleAssign = async (result: RosterSearchResult) => {
    if (!selectedCluster) return;
    const excluded = clusterPhotos.filter(p => !selected.has(p.face_id)).map(p => p.face_id);
    setIsAssigning(true);
    try {
      await photoTaggerClient.assignCluster(selectedCluster.id, result.player_name, result.jersey_number);
      if (excluded.length > 0) await photoTaggerClient.deassignFaces(excluded);

      const updated: ClusterWithAssignment = {
        ...selectedCluster,
        player_name: result.player_name,
        jersey_number: result.jersey_number,
      };
      setSelectedCluster(updated);
      setClusters(prev => prev.map(c => c.id === selectedCluster.id ? updated : c));
      setAssignSuccess(`${selected.size} photo${selected.size !== 1 ? 's' : ''} assigned to ${result.player_name} #${result.jersey_number}`);
      setSearchQuery('');
      setSearchResults([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Assignment failed');
    } finally { setIsAssigning(false); }
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && searchResults.length > 0) handleAssign(searchResults[0]);
    if (e.key === 'Escape') { setSearchQuery(''); setSearchResults([]); }
  };

  const unassigned = clusters.filter(c => !c.player_name);
  const assigned   = clusters.filter(c =>  c.player_name);
  const selectedCount = selected.size;

  return (
    <div className="w-full max-w-7xl mx-auto py-4 space-y-4">
      {/* Header */}
      <div>
        <h1 className="font-outfit text-4xl font-extrabold text-foreground">Cleanup Workspace</h1>
        <p className="mt-2 font-jakarta text-muted-fg">
          {unassigned.length} unassigned · {assigned.length} identified
        </p>
      </div>

      {error && (
        <div role="alert" aria-live="assertive"
          className="bg-white border-2 border-secondary rounded-xl shadow-pop-pink p-3 flex items-center justify-between">
          <p className="font-jakarta text-sm text-foreground">⚠️ {error}</p>
          <button onClick={() => setError(null)} className="font-jakarta text-xs text-muted-fg hover:text-foreground ml-4">×</button>
        </div>
      )}

      {/* ── Split screen ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4 items-start">

        {/* LEFT: cluster list */}
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop overflow-hidden">
          <div className="px-4 py-3 border-b-2 border-foreground bg-foreground">
            <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-white">Unassigned Stacks</p>
          </div>

          {isLoadingList ? (
            <div className="flex justify-center py-8"><LoadingSpinner message="Loading…" /></div>
          ) : clusters.length === 0 ? (
            <div className="p-6 text-center">
              <p className="font-outfit font-bold text-foreground text-sm">No face clusters</p>
              <p className="font-jakarta text-xs text-muted-fg mt-1">Run detection + grouping from the Players tab first</p>
            </div>
          ) : (
            <div className="divide-y-2 divide-frame max-h-[70vh] overflow-y-auto">
              {unassigned.map(c => (
                <ClusterRow key={c.id} cluster={c} isSelected={selectedCluster?.id === c.id} onClick={selectCluster} />
              ))}
              {assigned.length > 0 && (
                <>
                  <div className="px-4 py-2 bg-muted/40">
                    <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg">Identified ({assigned.length})</p>
                  </div>
                  {assigned.map(c => (
                    <ClusterRow key={c.id} cluster={c} isSelected={selectedCluster?.id === c.id} onClick={selectCluster} identified />
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* RIGHT: active workspace */}
        {!selectedCluster ? (
          <div className="bg-white border-2 border-frame rounded-2xl flex items-center justify-center p-16 text-center">
            <div>
              <svg width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="text-muted-fg mx-auto mb-3">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5" />
              </svg>
              <p className="font-outfit font-bold text-foreground">Select a cluster</p>
              <p className="font-jakarta text-xs text-muted-fg mt-1">Choose a stack from the left to review</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Cluster header */}
            <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop px-5 py-4 flex flex-wrap items-center gap-4">
              {selectedCluster.thumbnail_face_id && (
                <div className="w-12 h-12 rounded-full overflow-hidden border-2 border-foreground shadow-pop-sm flex-shrink-0">
                  <img src={photoTaggerClient.getFaceCropUrl(selectedCluster.thumbnail_face_id)} alt="" className="w-full h-full object-cover" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="font-outfit font-extrabold text-foreground">
                  {selectedCluster.player_name ?? `Cluster #${selectedCluster.id}`}
                </p>
                <p className="font-jakarta text-xs text-muted-fg">
                  {selectedCluster.photo_count} photos · {selectedCluster.face_count} detections
                  {selectedCluster.jersey_number && ` · #${selectedCluster.jersey_number}`}
                </p>
              </div>
              {assignSuccess && (
                <span role="status" className="font-jakarta text-xs text-quaternary font-bold bg-quaternary/10 px-3 py-1.5 rounded-full border border-quaternary">
                  ✓ {assignSuccess}
                </span>
              )}
            </div>

            {/* Photo grid */}
            <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop overflow-hidden">
              {/* Grid toolbar */}
              <div className="flex items-center justify-between px-4 py-3 border-b-2 border-foreground">
                <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg">
                  Active Stack · {selectedCount} of {clusterPhotos.length} selected
                </p>
                <div className="flex gap-2">
                  <button onClick={selectAll}   className="font-jakarta text-xs font-bold px-3 py-1 rounded-full border-2 border-frame hover:border-foreground hover:bg-muted transition-colors">All</button>
                  <button onClick={deselectAll} className="font-jakarta text-xs font-bold px-3 py-1 rounded-full border-2 border-frame hover:border-foreground hover:bg-muted transition-colors">None</button>
                </div>
              </div>

              {isLoadingPhotos ? (
                <div className="flex justify-center py-10"><LoadingSpinner message="Loading photos…" /></div>
              ) : clusterPhotos.length === 0 ? (
                <p className="py-8 text-center font-jakarta text-sm text-muted-fg">No photos in this cluster</p>
              ) : (
                <div className="p-3 grid grid-cols-4 sm:grid-cols-6 md:grid-cols-7 lg:grid-cols-8 xl:grid-cols-10 gap-2">
                  {clusterPhotos.map(photo => {
                    const src = photoTaggerClient.getPhotoUrl(photo.id);
                    const dim = imgDims.get(photo.id);
                    const isChecked = selected.has(photo.face_id);
                    return (
                      <div
                        key={photo.id}
                        className={`relative aspect-square rounded-lg overflow-hidden border-2 transition-all ${
                          isChecked ? 'border-accent shadow-pop-sm' : 'border-frame opacity-40'
                        }`}
                      >
                        <img
                          src={src}
                          alt={photo.filename}
                          className="w-full h-full object-cover"
                          onLoad={e => handleImgLoad(e, photo.id)}
                          onError={e => { e.currentTarget.style.display = 'none'; }}
                        />

                        {/* Face bounding box overlay */}
                        {dim && (
                          <div
                            className="absolute pointer-events-none"
                            style={{
                              ...bboxStyle(photo.face_bbox, dim),
                              border: '2px solid #FBBF24',
                              boxShadow: '0 0 0 1px rgba(0,0,0,0.4)',
                              boxSizing: 'border-box',
                            }}
                          />
                        )}

                        {/* Checkbox - top left */}
                        <button
                          onClick={() => togglePhoto(photo.face_id)}
                          aria-label={isChecked ? 'Deselect' : 'Select'}
                          className={`absolute top-1 left-1 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                            isChecked
                              ? 'bg-accent border-white'
                              : 'bg-white/80 border-frame'
                          }`}
                        >
                          {isChecked && (
                            <svg width="8" height="8" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 10 10">
                              <polyline points="1.5,5.5 4,8 8.5,2" />
                            </svg>
                          )}
                        </button>

                        {/* Enlarge button - top right */}
                        <button
                          onClick={() => { setModalPhoto(photo); setModalDim(dim ?? null); }}
                          aria-label="View full size"
                          className="absolute top-1 right-1 w-5 h-5 rounded bg-white/80 border border-frame flex items-center justify-center hover:bg-white transition-colors"
                        >
                          <svg width="8" height="8" fill="none" stroke="#1E293B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 10 10">
                            <path d="M1 4V1h3M6 1h3v3M9 6v3H6M4 9H1V6" />
                          </svg>
                        </button>

                        {/* Confidence badge - bottom */}
                        <div className="absolute bottom-0 left-0 right-0 bg-foreground/60 px-1 py-0.5 text-center">
                          <span className="font-jakarta text-white" style={{ fontSize: '9px' }}>
                            {Math.round(photo.face_confidence * 100)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Roster search + assign */}
            <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop overflow-hidden">
              <div className="px-4 py-3 border-b-2 border-foreground bg-foreground flex items-center justify-between">
                <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-white">Roster Search</p>
                {selectedCount > 0 && (
                  <span className="font-jakarta text-xs text-white/70">
                    Will assign {selectedCount} photo{selectedCount !== 1 ? 's' : ''}
                    {clusterPhotos.length - selectedCount > 0 && `, release ${clusterPhotos.length - selectedCount}`}
                  </span>
                )}
              </div>
              <div className="p-4 space-y-3">
                <div className="relative">
                  <input
                    ref={searchRef}
                    type="text"
                    value={searchQuery}
                    onChange={e => handleSearchChange(e.target.value)}
                    onKeyDown={handleSearchKeyDown}
                    placeholder="Type name or jersey # …"
                    disabled={isAssigning}
                    className="geo-input w-full px-4 py-2.5 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg pr-10 disabled:bg-muted"
                  />
                  {(isSearching || isAssigning) && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                      <span className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin block" />
                    </div>
                  )}
                </div>

                {searchResults.length > 0 && (
                  <div className="border-2 border-frame rounded-xl overflow-hidden divide-y divide-frame">
                    {searchResults.map((result, i) => (
                      <button
                        key={result.id}
                        onClick={() => handleAssign(result)}
                        disabled={isAssigning || selectedCount === 0}
                        className={`w-full text-left px-4 py-2.5 flex items-center gap-3 hover:bg-accent/5 transition-colors disabled:opacity-40 ${i === 0 ? 'bg-muted/20' : ''}`}
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

                {searchQuery && !isSearching && searchResults.length === 0 && (
                  <p className="font-jakarta text-xs text-muted-fg text-center py-2">
                    No match for "{searchQuery}" — add them on the Roster tab
                  </p>
                )}

                {selectedCount === 0 && clusterPhotos.length > 0 && (
                  <p className="font-jakarta text-xs text-secondary text-center">
                    Select at least one photo before assigning
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Full-size modal ─────────────────────────────────────────────────── */}
      {modalPhoto && (
        <div
          className="fixed inset-0 z-50 bg-foreground/80 flex items-center justify-center p-4"
          onClick={() => setModalPhoto(null)}
        >
          <div className="relative" onClick={e => e.stopPropagation()}>
            {/* Close */}
            <button
              onClick={() => setModalPhoto(null)}
              className="absolute -top-10 right-0 font-jakarta text-white font-bold text-sm flex items-center gap-1 hover:text-tertiary transition-colors"
            >
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 14 14"><path d="M1 1l12 12M13 1L1 13"/></svg>
              Close
            </button>

            {/* Photo + overlay — inline-block so wrapper hugs the img's rendered size */}
            <div className="relative inline-block rounded-xl overflow-hidden border-2 border-white shadow-pop-lg">
              <img
                src={photoTaggerClient.getPhotoUrl(modalPhoto.id)}
                alt={modalPhoto.filename}
                className="block max-w-[90vw] max-h-[85vh]"
                style={{ display: 'block' }}
                onLoad={e => {
                  const img = e.currentTarget;
                  setModalDim({ w: img.naturalWidth, h: img.naturalHeight });
                }}
              />

              {/* Face bbox overlay on full-size photo */}
              {modalDim && (
                <div
                  className="absolute pointer-events-none"
                  style={{
                    ...bboxStyle(modalPhoto.face_bbox, modalDim),
                    border: '3px solid #FBBF24',
                    boxShadow: '0 0 0 2px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(251,191,36,0.3)',
                    boxSizing: 'border-box',
                  }}
                />
              )}
            </div>

            {/* Caption */}
            <div className="mt-2 flex items-center justify-between px-1">
              <p className="font-jakarta text-white text-xs">{modalPhoto.filename}</p>
              <p className="font-jakarta text-white/60 text-xs">{Math.round(modalPhoto.face_confidence * 100)}% confidence</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Cluster list row ─────────────────────────────────────────────────────────
const ClusterRow: React.FC<{
  cluster: ClusterWithAssignment;
  isSelected: boolean;
  identified?: boolean;
  onClick: (c: ClusterWithAssignment) => void;
}> = ({ cluster, isSelected, identified, onClick }) => (
  <button
    onClick={() => onClick(cluster)}
    className={`w-full text-left px-4 py-3 flex items-center gap-3 transition-colors ${
      isSelected
        ? identified
          ? 'bg-quaternary/10 border-l-4 border-quaternary'
          : 'bg-accent/10 border-l-4 border-accent'
        : 'hover:bg-muted/40 border-l-4 border-transparent'
    }`}
  >
    <div className={`w-9 h-9 rounded-full overflow-hidden border-2 flex-shrink-0 ${identified ? 'border-quaternary' : 'border-foreground'} bg-muted`}>
      {cluster.thumbnail_face_id ? (
        <img src={photoTaggerClient.getFaceCropUrl(cluster.thumbnail_face_id)} alt="" className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center">
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="text-muted-fg">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
      )}
    </div>
    <div className="min-w-0 flex-1">
      <p className="font-outfit font-bold text-foreground text-xs leading-tight truncate">
        {cluster.player_name ?? `Cluster #${cluster.id}`}
      </p>
      <p className="font-jakarta text-xs text-muted-fg">
        {cluster.photo_count} photo{cluster.photo_count !== 1 ? 's' : ''}
        {cluster.jersey_number && ` · #${cluster.jersey_number}`}
      </p>
    </div>
    {isSelected && <span className="text-accent text-xs ml-auto">▶</span>}
  </button>
);

export default ReviewPage;
