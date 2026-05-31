import React, { useState, useEffect, useRef, useCallback } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from '../components/LoadingSpinner';
import type { ClusterPlayersResult, FaceDetectionResult, PlayerCluster, PlayerPhotoItem, RosterSearchResult } from '../types/index';
import { bboxStyle } from '../utils/bboxUtils';
import type { ImgDim } from '../utils/bboxUtils';

interface ClusterWithAssignment extends PlayerCluster {
  player_name?: string;
  jersey_number?: string;
  roster_entry_id?: number | null;
}

const MIN_REVIEW_FACE_CONFIDENCE = 0.6;

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
  const [writeMetadata, setWriteMetadata] = useState(() => window.localStorage.getItem('phototagger.writeMetadata') === 'true');

  // ── Detect + group pipeline ──────────────────────────────────────────────
  const [isDetecting, setIsDetecting] = useState(false);
  const [detectMsg,   setDetectMsg]   = useState<string | null>(null);

  // ── Hover-zoom lens (spec Scen B) ────────────────────────────────────────
  const [lens, setLens] = useState<{ photo: PlayerPhotoItem; x: number; y: number } | null>(null);

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

  // ── Detect faces + group into clusters ───────────────────────────────────
  const handleDetectAndGroup = async () => {
    setIsDetecting(true);
    setError(null);
    try {
      setDetectMsg('Detecting faces in photos…');
      const det = await photoTaggerClient.detectFaces();
      const detJob = await photoTaggerClient.pollJob<FaceDetectionResult>(det.job_id, {
        onUpdate: job => {
          if (job.status === 'running') setDetectMsg(`Detecting faces… ${job.progress}%`);
        },
      });
      const detResult = detJob.result;
      if (!detResult) {
        throw new Error('Face detection finished without a result');
      }

      setDetectMsg('Grouping faces into players…');
      const clu = await photoTaggerClient.clusterPlayers();
      const cluJob = await photoTaggerClient.pollJob<ClusterPlayersResult>(clu.job_id, {
        onUpdate: job => {
          if (job.status === 'running') setDetectMsg(`Grouping faces… ${job.progress}%`);
        },
      });
      const cluResult = cluJob.result;
      if (!cluResult) {
        throw new Error('Player grouping finished without a result');
      }

      setDetectMsg(`Built ${cluResult.clusters_created} groups from ${detResult.faces_detected} new faces`);
      await loadClusters();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Detection failed');
      setDetectMsg(null);
    } finally {
      setIsDetecting(false);
    }
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
      const data = await photoTaggerClient.getPlayerPhotos(cluster.id, { minFaceConfidence: MIN_REVIEW_FACE_CONFIDENCE });
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

  // ── Remove face from cluster permanently ────────────────────────────────
  const handleRemoveFace = useCallback(async (faceId: number) => {
    const photo = clusterPhotos.find(p => p.face_id === faceId);
    const clusterName = selectedCluster?.player_name ?? (selectedCluster ? `Cluster #${selectedCluster.id}` : 'this cluster');
    const confirmed = window.confirm(`Remove ${photo?.filename ?? 'this photo'} from ${clusterName}?`);
    if (!confirmed) return;

    try {
      const result = await photoTaggerClient.deassignFaces([faceId]);
      const remainingPhotos = clusterPhotos.filter(p => p.face_id !== faceId);
      setClusterPhotos(remainingPhotos);
      setSelected(prev => { const next = new Set(prev); next.delete(faceId); return next; });
      setLens(prev => prev?.photo.face_id === faceId ? null : prev);
      setModalPhoto(prev => prev?.face_id === faceId ? null : prev);

      if (selectedCluster && result.deleted_cluster_ids.includes(selectedCluster.id)) {
        setClusters(prev => prev.filter(c => c.id !== selectedCluster.id));
        setSelectedCluster(null);
        setClusterPhotos([]);
        setSelected(new Set());
        setImgDims(new Map());
        setAssignSuccess(null);
      } else {
        await loadClusters();
        if (selectedCluster) {
          setSelectedCluster(prev => prev ? {
            ...prev,
            face_count: Math.max(0, prev.face_count - 1),
            photo_count: remainingPhotos.length,
          } : prev);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove face');
    }
  }, [clusterPhotos, selectedCluster]);

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
    const selectedFaceIds = Array.from(selected);
    const excluded = clusterPhotos.filter(p => !selected.has(p.face_id)).map(p => p.face_id);
    setIsAssigning(true);
    try {
      const assignResult = await photoTaggerClient.assignCluster(
        selectedCluster.id,
        result.player_name,
        result.jersey_number,
        result.id,
        { writeMetadata, faceIds: selectedFaceIds },
      );
      if (excluded.length > 0) await photoTaggerClient.deassignFaces(excluded);

      const updated: ClusterWithAssignment = {
        ...selectedCluster,
        player_name: result.player_name,
        jersey_number: result.jersey_number,
        roster_entry_id: result.id,
      };
      setSelectedCluster(updated);
      setClusters(prev => prev.map(c => c.id === selectedCluster.id ? updated : c));
      const metadata = assignResult.metadata;
      const metadataText = metadata.requested
        ? ` · sidecars: ${metadata.written} written, ${metadata.skipped} skipped, ${metadata.failed} failed${metadata.opponent_omitted ? ' · opponent omitted' : ''}`
        : '';
      setAssignSuccess(`${selected.size} photo${selected.size !== 1 ? 's' : ''} assigned to ${result.player_name} #${result.jersey_number}${metadataText}`);
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
  const handleWriteMetadataChange = (checked: boolean) => {
    setWriteMetadata(checked);
    window.localStorage.setItem('phototagger.writeMetadata', checked ? 'true' : 'false');
  };

  return (
    <div className="w-full max-w-7xl mx-auto py-4 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-outfit text-4xl font-extrabold text-foreground">Cleanup Workspace</h1>
          <p className="mt-2 font-jakarta text-muted-fg">
            {unassigned.length} unassigned · {assigned.length} identified
          </p>
        </div>
        <div className="flex items-center gap-3">
          {detectMsg && (
            <span role="status" className="font-jakarta text-xs text-muted-fg">{detectMsg}</span>
          )}
          <button
            onClick={handleDetectAndGroup}
            disabled={isDetecting}
            className="btn-candy bg-accent text-white font-jakarta font-bold text-sm px-5 py-2.5 rounded-full border-2 border-foreground shadow-pop disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
          >
            {isDetecting ? (
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin block" />
            ) : (
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
              </svg>
            )}
            {isDetecting ? 'Working…' : 'Detect & Group Faces'}
          </button>
        </div>
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
            <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-white">Face Clusters</p>
          </div>

          {isLoadingList ? (
            <div className="flex justify-center py-8"><LoadingSpinner message="Loading…" /></div>
          ) : clusters.length === 0 ? (
            <div className="p-6 text-center">
              <p className="font-outfit font-bold text-foreground text-sm">No face clusters yet</p>
              <p className="font-jakarta text-xs text-muted-fg mt-1">Click <span className="font-bold text-foreground">Detect &amp; Group Faces</span> above to build clusters from your photos</p>
            </div>
          ) : (
            <div className="divide-y-2 divide-frame max-h-[70vh] overflow-y-auto">
              {unassigned.length > 0 && (
                <div className="px-4 py-2 bg-muted/40">
                  <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg">Unassigned ({unassigned.length})</p>
                </div>
              )}
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
                        onMouseEnter={e => setLens({ photo, x: e.clientX, y: e.clientY })}
                        onMouseMove={e => setLens({ photo, x: e.clientX, y: e.clientY })}
                        onMouseLeave={() => setLens(null)}
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

                        {/* Purple face bbox — 5px buffer, border sits outside the face */}
                        {dim && (
                          <div
                            className="absolute pointer-events-none"
                            style={{
                              ...bboxStyle(photo.face_bbox, dim, 7),
                              border: '2px solid #A855F7',
                              background: 'transparent',
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

                        {/* Confidence badge + remove button - bottom */}
                        <div className="absolute bottom-0 left-0 right-0 bg-foreground/60 px-1 py-0.5 flex items-center justify-between gap-1">
                          <button
                            onClick={e => { e.stopPropagation(); handleRemoveFace(photo.face_id); }}
                            aria-label="Remove from cluster"
                            title="Remove this face from the cluster"
                            className="w-3.5 h-3.5 rounded-sm bg-secondary/90 flex items-center justify-center flex-shrink-0 hover:bg-secondary transition-colors"
                          >
                            <svg width="6" height="6" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 6 6">
                              <path d="M1 1l4 4M5 1L1 5"/>
                            </svg>
                          </button>
                          <span className="font-jakarta text-white flex-1 text-center" style={{ fontSize: '9px' }}>
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
              <div className="px-4 py-3 border-b-2 border-foreground bg-foreground">
                <div className="flex items-center justify-between mb-2">
                  <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-white">Match to Roster</p>
                  {selectedCount > 0 && (
                    <span className="font-jakarta text-xs text-white/70">
                      {selectedCount} photo{selectedCount !== 1 ? 's' : ''} selected
                    </span>
                  )}
                </div>
                <p className="font-jakarta text-xs text-white/80">Select a roster entry to pull metadata into sidecar files</p>
              </div>
              <div className="p-4 space-y-3">
                <label className="flex items-center justify-between gap-3 rounded-xl border-2 border-frame bg-muted/20 px-3 py-2">
                  <span>
                    <span className="block font-jakarta text-xs font-bold text-foreground">Write XMP sidecar metadata</span>
                    <span className="block font-jakarta text-[11px] text-muted-fg">Player, team, year, and opponent to each photo</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={writeMetadata}
                    onChange={e => handleWriteMetadataChange(e.target.checked)}
                    className="h-4 w-4 accent-accent"
                  />
                </label>
                <div className="relative">
                  <input
                    ref={searchRef}
                    type="text"
                    value={searchQuery}
                    onChange={e => handleSearchChange(e.target.value)}
                    onKeyDown={handleSearchKeyDown}
                    placeholder="Find player by name or jersey…"
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
                  <div className="space-y-2">
                    <p className="font-jakarta text-xs font-bold text-muted-fg uppercase">Roster entries found</p>
                    <div className="border-2 border-frame rounded-xl overflow-hidden divide-y divide-frame">
                      {searchResults.map((result, i) => (
                        <button
                          key={result.id}
                          onClick={() => handleAssign(result)}
                          disabled={isAssigning || selectedCount === 0}
                          className={`w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:hover:bg-transparent ${i === 0 ? 'bg-accent/5 border-l-4 border-l-accent' : ''}`}
                        >
                          <span className="w-10 h-10 bg-accent rounded-lg border-2 border-foreground shadow-pop-sm flex items-center justify-center flex-shrink-0">
                            <span className="font-outfit font-extrabold text-white text-sm leading-none">#{result.jersey_number}</span>
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="font-outfit font-bold text-foreground text-sm">{result.player_name}</p>
                            <p className="font-jakarta text-xs text-muted-fg">
                              {result.team_name}
                              {result.uniform_color && ` · ${result.uniform_color}`}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            {i === 0 && (
                              <span className="font-jakarta text-xs text-muted-fg bg-muted px-2 py-0.5 rounded border border-frame whitespace-nowrap">↵ Enter</span>
                            )}
                            <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" className="text-muted-fg flex-shrink-0">
                              <polyline points="9 18 15 12 9 6"></polyline>
                            </svg>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {searchQuery && !isSearching && searchResults.length === 0 && (
                  <p className="font-jakarta text-xs text-secondary text-center py-3 bg-secondary/5 rounded-lg border border-secondary/20">
                    No roster entry found for "{searchQuery}"<br/>
                    <span className="text-muted-fg text-[11px]">Add new players on the Roster tab</span>
                  </p>
                )}

                {selectedCount === 0 && clusterPhotos.length > 0 && (
                  <p className="font-jakarta text-xs text-secondary text-center py-3 bg-secondary/5 rounded-lg border border-secondary/20">
                    Select at least one photo before assigning
                  </p>
                )}

                {!searchQuery && searchResults.length === 0 && selectedCount > 0 && (
                  <p className="font-jakarta text-xs text-muted-fg text-center py-2">
                    Start typing to search available players
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Hover-zoom lens (spec Scen B) ───────────────────────────────────── */}
      {lens && !modalPhoto && (() => {
        const dim = imgDims.get(lens.photo.id);
        const W = 300;
        const left = Math.min(lens.x + 24, window.innerWidth  - W - 16);
        const top  = Math.min(lens.y + 24, window.innerHeight - W - 48);
        return (
          <div className="fixed z-40 pointer-events-none" style={{ left, top, width: W }}>
            <div className="relative inline-block rounded-xl overflow-hidden border-2 border-foreground shadow-pop-lg bg-white">
              <img src={photoTaggerClient.getPhotoUrl(lens.photo.id)} alt="" className="block" style={{ width: W }} />
              {dim && (
                <div
                  className="absolute pointer-events-none"
                  style={{
                    ...bboxStyle(lens.photo.face_bbox, dim, 8),
                    border: '3px solid #A855F7',
                    background: 'transparent',
                    boxSizing: 'border-box',
                  }}
                />
              )}
              <div className="absolute bottom-0 left-0 right-0 bg-foreground/80 px-2 py-1 flex items-center justify-between">
                <span className="font-jakarta text-white truncate" style={{ fontSize: '10px' }}>{lens.photo.filename}</span>
                <span className="font-jakarta text-white flex-shrink-0 ml-2" style={{ fontSize: '10px' }}>{Math.round(lens.photo.face_confidence * 100)}%</span>
              </div>
            </div>
          </div>
        );
      })()}

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
                    ...bboxStyle(modalPhoto.face_bbox, modalDim, 8),
                    border: '3px solid #A855F7',
                    background: 'transparent',
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
