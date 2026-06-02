import React, { useState, useEffect, useRef, useCallback } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from '../components/LoadingSpinner';
import { SidebarLayout } from '../components/SidebarLayout';
import { HierarchicalSidebar } from '../components/HierarchicalSidebar';
import { useSidebar } from '../contexts/SidebarContext';
import type { ClusterPlayersResult, FaceDetectionResult, MatchSimilarResponse, PlayerCluster, PlayerPhotoItem, RosterSearchResult, SimilarClusterMatch, PhotoBatch, BatchesResponse } from '../types/index';
import { bboxStyle } from '../utils/bboxUtils';
import type { ImgDim } from '../utils/bboxUtils';

interface ClusterWithAssignment extends PlayerCluster {
  player_name?: string;
  jersey_number?: string;
  roster_entry_id?: number | null;
  selected?: boolean;
}

const MIN_REVIEW_FACE_CONFIDENCE = 0.6;

export const ReviewPage: React.FC = () => {
  const { selectedGame } = useSidebar();
  // ── Batches ─────────────────────────────────────────────────────────────
  const [batches, setBatches] = useState<PhotoBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null);
  const [isLoadingBatches, setIsLoadingBatches] = useState(true);

  // ── Cluster list ────────────────────────────────────────────────────────
  const [clusters,        setClusters]        = useState<ClusterWithAssignment[]>([]);
  const [selectedCluster, setSelectedCluster] = useState<ClusterWithAssignment | null>(null);
  const [clusterPhotos,   setClusterPhotos]   = useState<PlayerPhotoItem[]>([]);
  const [isLoadingList,   setIsLoadingList]   = useState(true);
  const [isLoadingPhotos, setIsLoadingPhotos] = useState(false);

  // ── Cluster bulk selection (select multiple clusters for batch assignment) ──
  const [bulkSelectedClusters, setBulkSelectedClusters] = useState<Set<number>>(new Set());

  // ── Selected faces within a cluster ──────────────────────────────────────
  // Keyed by face_id; true = included in assign, false = excluded
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // ── Image natural dims for bbox overlay ─────────────────────────────────
  const [imgDims, setImgDims] = useState<Map<number, ImgDim>>(new Map());

  // ── Full-size modal ─────────────────────────────────────────────────────
  const [modalPhoto,  setModalPhoto]  = useState<PlayerPhotoItem | null>(null);
  const [modalDim,    setModalDim]    = useState<ImgDim | null>(null);

  // ── Suggestion photo modal ───────────────────────────────────────────────
  const [suggestionModalPhoto, setSuggestionModalPhoto] = useState<SimilarClusterMatch | null>(null);
  const [suggestionModalDim,   setSuggestionModalDim]   = useState<ImgDim | null>(null);

  // ── Roster search ────────────────────────────────────────────────────────
  const [searchQuery,   setSearchQuery]   = useState('');
  const [searchResults, setSearchResults] = useState<RosterSearchResult[]>([]);
  const [isSearching,   setIsSearching]   = useState(false);
  const [assignSuccess, setAssignSuccess] = useState<string | null>(null);
  const [error,         setError]         = useState<string | null>(null);
  const [isAssigning,   setIsAssigning]   = useState(false);
  const [writeMetadata, setWriteMetadata] = useState(() => window.localStorage.getItem('phototagger.writeMetadata') === 'true');

  // ── Post-assign similarity matches ───────────────────────────────────────
  const [matchResults,      setMatchResults]      = useState<MatchSimilarResponse | null>(null);
  const [isMatching,        setIsMatching]        = useState(false);
  const [dismissedSuggestions, setDismissedSuggestions] = useState<Set<number>>(new Set());

  // ── Detect + group pipeline ──────────────────────────────────────────────
  const [isDetecting, setIsDetecting] = useState(false);
  const [detectMsg,   setDetectMsg]   = useState<string | null>(null);
  const [currentDetectFile, setCurrentDetectFile] = useState<string | null>(null);

  // ── Hover-zoom lens (spec Scen B) ────────────────────────────────────────
  const [lens, setLens] = useState<{ photo: PlayerPhotoItem; x: number; y: number } | null>(null);

  const searchRef   = useRef<HTMLInputElement>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Load batches and clusters ────────────────────────────────────────────
  useEffect(() => {
    loadBatches();
    loadClusters();
  }, []);

  // ── Update batch when game is selected from sidebar ───────────────────────
  useEffect(() => {
    if (selectedGame) {
      const batch = batches.find(b => b.source_folder === selectedGame);
      if (batch) {
        setSelectedBatchId(batch.id);
      }
    }
  }, [selectedGame, batches]);

  const loadBatches = async () => {
    setIsLoadingBatches(true);
    try {
      const data = await photoTaggerClient.getBatches();
      setBatches(data.batches);
      // Auto-select first batch
      if (data.batches.length > 0 && !selectedBatchId) {
        setSelectedBatchId(data.batches[0].id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load batches');
    } finally { setIsLoadingBatches(false); }
  };

  const loadClusters = async () => {
    setIsLoadingList(true);
    try {
      const data = await photoTaggerClient.getPlayers();
      setClusters((data.players as ClusterWithAssignment[]).map(c => ({ ...c, selected: false })));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load clusters');
    } finally { setIsLoadingList(false); }
  };

  // ── Detect faces + group into clusters ───────────────────────────────────
  const handleDetectAndGroup = async () => {
    setIsDetecting(true);
    setError(null);
    setCurrentDetectFile(null);
    try {
      setDetectMsg('Detecting faces in photos…');
      const det = await photoTaggerClient.detectFaces();
      const detJob = await photoTaggerClient.pollJob<FaceDetectionResult>(det.job_id, {
        onUpdate: job => {
          if (job.status === 'running') {
            // Display current file if available, otherwise just percentage
            const currentFile = (job.result as any)?.current_file;
            if (currentFile) {
              setDetectMsg(`Detected faces in ${currentFile}`);
              setCurrentDetectFile(currentFile);
            } else {
              setDetectMsg(`Detecting faces… ${job.progress}%`);
            }
          }
        },
      });
      const detResult = detJob.result;
      if (!detResult) {
        throw new Error('Face detection finished without a result');
      }

      setDetectMsg('Grouping faces into players…');
      setCurrentDetectFile(null);
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
      setCurrentDetectFile(null);
      await loadClusters();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Detection failed');
      setDetectMsg(null);
      setCurrentDetectFile(null);
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
    setMatchResults(null);
    setDismissedSuggestions(new Set());
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

      // Scan remaining clusters for similar faces
      setIsMatching(true);
      try {
        const matches = await photoTaggerClient.matchSimilarClusters(selectedCluster.id);
        setMatchResults(matches);
        // Remove auto-tagged clusters from the unassigned list in local state
        if (matches.auto_tagged.length > 0) {
          const autoTaggedIds = new Set(matches.auto_tagged.map(m => m.cluster_id));
          setClusters(prev => prev.map(c =>
            autoTaggedIds.has(c.id)
              ? { ...c, player_name: result.player_name, jersey_number: result.jersey_number, roster_entry_id: result.id }
              : c
          ));
        }
      } catch {
        // Similarity scan is best-effort — don't surface errors to the user
      } finally {
        setIsMatching(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Assignment failed');
    } finally { setIsAssigning(false); }
  };

  // ── Confirm a suggested cluster ──────────────────────────────────────────
  const handleConfirmSuggestion = async (suggestion: SimilarClusterMatch, result: RosterSearchResult) => {
    try {
      await photoTaggerClient.assignCluster(
        suggestion.cluster_id,
        result.player_name,
        result.jersey_number,
        result.id,
        { faceIds: [] },
      );
      setClusters(prev => prev.map(c =>
        c.id === suggestion.cluster_id
          ? { ...c, player_name: result.player_name, jersey_number: result.jersey_number, roster_entry_id: result.id }
          : c
      ));
      setMatchResults(prev => prev ? {
        ...prev,
        suggestions: prev.suggestions.filter(s => s.cluster_id !== suggestion.cluster_id),
      } : prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to confirm suggestion');
    }
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && searchResults.length > 0) handleAssign(searchResults[0]);
    if (e.key === 'Escape') { setSearchQuery(''); setSearchResults([]); }
  };

  const handleWriteMetadataChange = (checked: boolean) => {
    setWriteMetadata(checked);
    window.localStorage.setItem('phototagger.writeMetadata', checked ? 'true' : 'false');
  };

  // Batch stats
  const currentBatch = batches.find(b => b.id === selectedBatchId);
  const unassignedClusters = clusters.filter(c => !c.player_name);
  const assignedClusters = clusters.filter(c => c.player_name);
  const bulkSelectedCount = bulkSelectedClusters.size;
  const selectedCount = selected.size;

  return (
    <SidebarLayout
      sidebar={
        <HierarchicalSidebar
          pageType="review"
          batches={batches}
        />
      }
      children={
        <div className="w-full h-screen flex flex-col bg-cream overflow-hidden">
          {/* Header with batch selector */}
          <header className="border-b-2 border-foreground bg-white px-4 py-3 flex flex-col gap-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-outfit text-2xl font-extrabold text-foreground">Review & Assign</h1>
            {currentBatch && (
              <p className="font-jakarta text-xs text-muted-fg mt-1">
                Batch: <span className="font-bold text-foreground">{currentBatch.source_folder}</span>
                <span className="mx-2">·</span>
                {unassignedClusters.length} unassigned • {assignedClusters.length} assigned
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-2">
            <button
              onClick={handleDetectAndGroup}
              disabled={isDetecting}
              className="btn-candy bg-accent text-white font-jakarta font-bold text-xs px-3 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
            >
              {isDetecting ? (
                <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin block" />
              ) : (
                <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                  <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
                </svg>
              )}
              {isDetecting ? 'Working…' : 'Detect'}
            </button>
            {detectMsg && (
              <span role="status" className="font-jakarta text-xs text-muted-fg text-right break-words whitespace-normal">{detectMsg}</span>
            )}
          </div>
        </div>

        {/* Global metadata writing setting */}
        <label className="flex items-center gap-2 rounded border-2 border-frame bg-muted/20 px-3 py-2 w-fit group relative">
          <input
            type="checkbox"
            checked={writeMetadata}
            onChange={e => handleWriteMetadataChange(e.target.checked)}
            className="h-3 w-3 accent-accent"
          />
          <span>
            <span className="block font-jakarta text-xs font-bold text-foreground">Write clear data back to photo</span>
          </span>
          <button
            type="button"
            className="ml-2 flex-shrink-0 text-muted-fg hover:text-foreground transition-colors flex items-center justify-center"
            aria-label="What gets written back to photos"
            title="Player name, jersey number, and confidence metadata written to XMP sidecars"
          >
            <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <circle cx="12" cy="8" r="0.5" fill="currentColor" />
            </svg>
          </button>
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-foreground text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap font-jakarta">
            Writes player name, jersey, and confidence to XMP sidecars
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-foreground" />
          </div>
        </label>
      </header>

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT: Cluster list sidebar */}
        <div className="w-64 bg-white border-r-2 border-foreground flex flex-col overflow-hidden flex-shrink-0">

          <div className="px-3 py-2 border-b-2 border-foreground bg-foreground flex items-center justify-between">
            <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-white">Clusters</p>
            <span className="text-white text-xs">{unassignedClusters.length} unassigned</span>
          </div>

          {isLoadingList ? (
            <div className="flex justify-center py-6"><LoadingSpinner message="Loading…" /></div>
          ) : clusters.length === 0 ? (
            <div className="p-4 text-center flex-1 flex items-center justify-center">
              <div>
                <p className="font-outfit font-bold text-foreground text-xs">No clusters yet</p>
                <p className="font-jakarta text-xs text-muted-fg mt-1">Run detection above</p>
              </div>
            </div>
          ) : (
            <div className="overflow-y-auto flex-1 divide-y divide-frame">
              {unassignedClusters.map(c => (
                <ClusterRowWithCheckbox
                  key={c.id}
                  cluster={c}
                  isSelected={selectedCluster?.id === c.id}
                  isBulkSelected={bulkSelectedClusters.has(c.id)}
                  onSelect={() => selectCluster(c)}
                  onToggleBulk={() => {
                    const next = new Set(bulkSelectedClusters);
                    next.has(c.id) ? next.delete(c.id) : next.add(c.id);
                    setBulkSelectedClusters(next);
                  }}
                />
              ))}
              {assignedClusters.length > 0 && (
                <>
                  <div className="px-3 py-2 bg-muted/40 sticky top-0">
                    <p className="font-jakarta text-xs font-bold text-muted-fg">IDENTIFIED ({assignedClusters.length})</p>
                  </div>
                  {assignedClusters.map(c => (
                    <ClusterRowWithCheckbox
                      key={c.id}
                      cluster={c}
                      isSelected={selectedCluster?.id === c.id}
                      isBulkSelected={false}
                      onSelect={() => selectCluster(c)}
                      onToggleBulk={() => {}}
                      identified
                    />
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* CENTER + RIGHT: Photo grid + Assignment drawer */}
        <div className="flex-1 flex overflow-hidden">
          {/* CENTER: Photo grid */}
          <div className="flex-1 flex flex-col overflow-hidden bg-muted/20">
            {!selectedCluster ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center">
                  <svg width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="text-muted-fg mx-auto mb-3">
                    <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="12" cy="12" r="3" />
                  </svg>
                  <p className="font-outfit font-bold text-foreground">Select a cluster</p>
                  <p className="font-jakarta text-xs text-muted-fg mt-1">Choose from the left to review photos</p>
                </div>
              </div>
            ) : (
              <div className="flex flex-col overflow-hidden">
                {/* Grid header */}
                <div className="px-4 py-3 border-b border-frame bg-white flex items-center justify-between flex-shrink-0">
                  <div className="min-w-0 flex-1">
                    <p className="font-outfit font-bold text-foreground text-sm truncate">
                      {selectedCluster.player_name || `Cluster #${selectedCluster.id}`}
                    </p>
                    <p className="font-jakarta text-xs text-muted-fg">
                      {selectedCount} of {clusterPhotos.length} photos selected
                    </p>
                  </div>
                  <div className="flex gap-2 ml-4">
                    <button onClick={selectAll} className="font-jakarta text-xs px-2 py-1 rounded border border-frame hover:bg-muted">All</button>
                    <button onClick={deselectAll} className="font-jakarta text-xs px-2 py-1 rounded border border-frame hover:bg-muted">None</button>
                  </div>
                </div>

                {/* Photo grid */}
                <div className="flex-1 overflow-auto p-3">
                  {isLoadingPhotos ? (
                    <div className="flex justify-center py-10"><LoadingSpinner message="Loading photos…" /></div>
                  ) : clusterPhotos.length === 0 ? (
                    <p className="text-center font-jakarta text-sm text-muted-fg py-10">No photos in this cluster</p>
                  ) : (
                    <div className="grid grid-cols-auto gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))' }}>
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
                            className={`relative aspect-square rounded-lg overflow-hidden border-2 transition-all cursor-pointer ${
                              isChecked ? 'border-accent shadow-pop-sm' : 'border-frame opacity-50 hover:opacity-70'
                            }`}
                            onClick={() => togglePhoto(photo.face_id)}
                          >
                            <img
                              src={src}
                              alt={photo.filename}
                              className="w-full h-full object-cover"
                              onLoad={e => handleImgLoad(e, photo.id)}
                              onError={e => { e.currentTarget.style.display = 'none'; }}
                            />

                            {dim && (
                              <div
                                className="absolute pointer-events-none"
                                style={{
                                  ...bboxStyle(photo.face_bbox, dim, 5),
                                  border: '2px solid #A855F7',
                                  background: 'transparent',
                                  boxSizing: 'border-box',
                                }}
                              />
                            )}

                            <div className="absolute top-1 left-1 w-4 h-4 rounded border-2 flex items-center justify-center bg-white/80 border-frame">
                              {isChecked && (
                                <svg width="7" height="7" fill="none" stroke="#06B6D4" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 10 10">
                                  <polyline points="1.5,5.5 4,8 8.5,2" />
                                </svg>
                              )}
                            </div>

                            <div className="absolute bottom-0 left-0 right-0 bg-foreground/70 px-1 py-0.5">
                              <span className="font-jakarta text-white text-[8px]">
                                {Math.round(photo.face_confidence * 100)}%
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* RIGHT: Assignment drawer */}
          {selectedCluster && (
            <div className="w-80 bg-white border-l-2 border-foreground flex flex-col overflow-hidden flex-shrink-0">
              <div className="px-3 py-3 border-b border-frame bg-foreground">
                <p className="font-jakarta text-xs font-bold uppercase tracking-wider text-white mb-2">Assign Player</p>
                {assignSuccess && (
                  <span role="status" className="font-jakarta text-xs text-quaternary font-bold bg-quaternary/10 px-2 py-1 rounded border border-quaternary inline-block">
                    ✓ {assignSuccess}
                  </span>
                )}
              </div>

              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                <div className="relative">
                  <input
                    ref={searchRef}
                    type="text"
                    value={searchQuery}
                    onChange={e => handleSearchChange(e.target.value)}
                    onKeyDown={handleSearchKeyDown}
                    placeholder="Search player…"
                    disabled={isAssigning}
                    className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-lg font-jakarta text-sm text-foreground placeholder:text-muted-fg pr-8 disabled:bg-muted"
                  />
                  {(isSearching || isAssigning) && (
                    <div className="absolute right-2 top-1/2 -translate-y-1/2">
                      <span className="w-3 h-3 border-2 border-accent border-t-transparent rounded-full animate-spin block" />
                    </div>
                  )}
                </div>

                {searchResults.length > 0 && (
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {searchResults.map((result, i) => (
                      <button
                        key={result.id}
                        onClick={() => handleAssign(result)}
                        disabled={isAssigning || selectedCount === 0}
                        className={`w-full text-left px-2 py-2 rounded text-sm flex items-center gap-2 transition-colors disabled:opacity-40 ${
                          i === 0 ? 'bg-accent/10 border border-accent' : 'hover:bg-muted border border-transparent'
                        }`}
                      >
                        <span className="w-7 h-7 bg-accent rounded flex items-center justify-center flex-shrink-0">
                          <span className="font-outfit font-bold text-white text-xs">#{result.jersey_number}</span>
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="font-outfit font-bold text-foreground text-xs">{result.player_name}</p>
                          <p className="font-jakarta text-xs text-muted-fg truncate">{result.team_name}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {!searchQuery && searchResults.length === 0 && (
                  <p className="font-jakarta text-xs text-muted-fg text-center py-2">Start typing to search</p>
                )}

                {searchQuery && !isSearching && searchResults.length === 0 && (
                  <p className="font-jakarta text-xs text-secondary text-center py-2">No matches found</p>
                )}

                {/* ── Similarity scan results ─────────────────────────────── */}
                {isMatching && (
                  <div className="flex items-center gap-2 py-2">
                    <span className="w-3 h-3 border-2 border-accent border-t-transparent rounded-full animate-spin block flex-shrink-0" />
                    <span className="font-jakarta text-xs text-muted-fg">Scanning for similar faces…</span>
                  </div>
                )}

                {matchResults && !isMatching && (
                  <div className="space-y-2">
                    {/* Auto-tagged banner */}
                    {matchResults.auto_tagged.length > 0 && (
                      <div className="bg-quaternary/10 border border-quaternary rounded-lg px-3 py-2">
                        <p className="font-jakarta text-xs font-bold text-quaternary">
                          ✓ Auto-tagged {matchResults.auto_tagged.length} more cluster{matchResults.auto_tagged.length !== 1 ? 's' : ''} as {selectedCluster?.player_name}
                        </p>
                        <p className="font-jakarta text-[10px] text-muted-fg mt-0.5">
                          All had ≥60% face similarity
                        </p>
                      </div>
                    )}

                    {/* Suggestions requiring user confirmation */}
                    {matchResults.suggestions.filter(s => !dismissedSuggestions.has(s.cluster_id)).length > 0 && (
                      <div className="space-y-1.5">
                        <p className="font-jakarta text-[10px] font-bold uppercase tracking-wider text-muted-fg">
                          Possible matches — confirm?
                        </p>
                        {matchResults.suggestions
                          .filter(s => !dismissedSuggestions.has(s.cluster_id))
                          .map(suggestion => (
                          <div
                            key={suggestion.cluster_id}
                            className="bg-tertiary/10 border border-tertiary rounded-lg px-2 py-2 space-y-1.5"
                          >
                            <div className="flex items-center gap-2">
                              {suggestion.thumbnail_face_id ? (
                                <img
                                  src={photoTaggerClient.getFaceCropUrl(suggestion.thumbnail_face_id)}
                                  alt="face"
                                  className="w-8 h-8 rounded-full border border-frame object-cover flex-shrink-0"
                                />
                              ) : (
                                <div className="w-8 h-8 rounded-full border border-frame bg-muted flex-shrink-0" />
                              )}
                              <div className="min-w-0 flex-1">
                                <p className="font-jakarta text-xs font-bold text-foreground">
                                  Cluster #{suggestion.cluster_id}
                                </p>
                                <p className="font-jakarta text-[10px] text-muted-fg">
                                  {suggestion.face_count} face{suggestion.face_count !== 1 ? 's' : ''} · {Math.round(suggestion.similarity * 100)}% match
                                </p>
                              </div>
                            </div>
                            <p className="font-jakarta text-[10px] text-foreground">
                              Tag as <span className="font-bold">{selectedCluster?.player_name} #{selectedCluster?.jersey_number}</span>?
                            </p>
                            <div className="flex gap-1.5">
                              <button
                                onClick={() => {
                                  if (selectedCluster?.roster_entry_id != null) {
                                    handleConfirmSuggestion(suggestion, {
                                      id: selectedCluster.roster_entry_id,
                                      player_name: selectedCluster.player_name!,
                                      jersey_number: selectedCluster.jersey_number!,
                                      team_name: '',
                                    });
                                  }
                                }}
                                className="flex-1 btn-candy bg-accent text-white font-jakarta font-bold text-[10px] px-2 py-1 rounded-full border border-foreground shadow-pop-sm"
                              >
                                Yes, tag
                              </button>
                              <button
                                onClick={() => {
                                  setSuggestionModalPhoto(suggestion);
                                  setSuggestionModalDim(null);
                                }}
                                className="flex-1 font-jakarta text-[10px] px-2 py-1 rounded-full border border-accent text-accent hover:bg-accent/10"
                              >
                                Enlarge
                              </button>
                              <button
                                onClick={() => setDismissedSuggestions(prev => new Set([...prev, suggestion.cluster_id]))}
                                className="flex-1 font-jakarta text-[10px] px-2 py-1 rounded-full border border-frame text-muted-fg hover:bg-muted"
                              >
                                Skip
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* All suggestions dismissed or none */}
                    {matchResults.suggestions.length > 0 &&
                      matchResults.suggestions.every(s => dismissedSuggestions.has(s.cluster_id)) && (
                      <p className="font-jakarta text-[10px] text-muted-fg text-center py-1">All suggestions reviewed.</p>
                    )}

                    {matchResults.auto_tagged.length === 0 && matchResults.suggestions.length === 0 && (
                      <p className="font-jakarta text-[10px] text-muted-fg text-center py-1">No similar unidentified clusters found.</p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
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

      {/* ── Suggestion photo modal ──────────────────────────────────────────── */}
      {suggestionModalPhoto && suggestionModalPhoto.photo_id && (
        <div
          className="fixed inset-0 z-50 bg-foreground/80 flex items-center justify-center p-4"
          onClick={() => {
            setSuggestionModalPhoto(null);
            setSuggestionModalDim(null);
          }}
        >
          <div className="relative" onClick={e => e.stopPropagation()}>
            {/* Close */}
            <button
              onClick={() => {
                setSuggestionModalPhoto(null);
                setSuggestionModalDim(null);
              }}
              className="absolute -top-10 right-0 font-jakarta text-white font-bold text-sm flex items-center gap-1 hover:text-tertiary transition-colors"
            >
              <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 14 14"><path d="M1 1l12 12M13 1L1 13"/></svg>
              Close
            </button>

            {/* Photo + overlay */}
            <div className="relative inline-block rounded-xl overflow-hidden border-2 border-white shadow-pop-lg">
              <img
                src={photoTaggerClient.getPhotoUrl(suggestionModalPhoto.photo_id)}
                alt="suggestion photo"
                className="block max-w-[90vw] max-h-[85vh]"
                style={{ display: 'block' }}
                onLoad={e => {
                  const img = e.currentTarget;
                  setSuggestionModalDim({ w: img.naturalWidth, h: img.naturalHeight });
                }}
              />

              {/* Face bbox overlay with purple border and buffering */}
              {suggestionModalDim && suggestionModalPhoto.face_bbox && (
                <div
                  className="absolute pointer-events-none"
                  style={{
                    ...bboxStyle(suggestionModalPhoto.face_bbox as [number, number, number, number], suggestionModalDim, 8),
                    border: '3px solid #A855F7',
                    background: 'transparent',
                    boxSizing: 'border-box',
                  }}
                />
              )}
            </div>

            {/* Caption */}
            <div className="mt-2 flex items-center justify-between px-1">
              <p className="font-jakarta text-white text-xs">Cluster #{suggestionModalPhoto.cluster_id}</p>
              <p className="font-jakarta text-white/60 text-xs">{Math.round(suggestionModalPhoto.similarity * 100)}% match</p>
            </div>
          </div>
        </div>
      )}
    </div>
      }
    />
  );
};

// ── Cluster row with checkbox for bulk selection ──────────────────────────
const ClusterRowWithCheckbox: React.FC<{
  cluster: ClusterWithAssignment;
  isSelected: boolean;
  isBulkSelected: boolean;
  identified?: boolean;
  onSelect: () => void;
  onToggleBulk: () => void;
}> = ({ cluster, isSelected, isBulkSelected, identified, onSelect, onToggleBulk }) => (
  <div
    onClick={onSelect}
    className={`w-full text-left px-2 py-2 flex items-center gap-2 transition-colors border-l-4 cursor-pointer ${
      isSelected
        ? identified
          ? 'bg-quaternary/10 border-quaternary'
          : 'bg-accent/10 border-accent'
        : 'hover:bg-muted/30 border-transparent'
    }`}
  >
    {!identified && (
      <div
        onClick={e => { e.stopPropagation(); onToggleBulk(); }}
        className={`flex-shrink-0 w-4 h-4 rounded border-2 flex items-center justify-center transition-colors cursor-pointer ${
          isBulkSelected ? 'bg-accent border-accent' : 'border-frame hover:border-foreground'
        }`}
        role="checkbox"
        aria-checked={isBulkSelected}
      >
        {isBulkSelected && (
          <svg width="6" height="6" fill="none" stroke="white" strokeWidth="2.5" viewBox="0 0 10 10">
            <polyline points="1.5,5.5 4,8 8.5,2" />
          </svg>
        )}
      </div>
    )}

    <div className={`w-7 h-7 rounded-full overflow-hidden border-2 flex-shrink-0 ${identified ? 'border-quaternary' : 'border-foreground'} bg-muted`}>
      {cluster.thumbnail_face_id ? (
        <img src={photoTaggerClient.getFaceCropUrl(cluster.thumbnail_face_id)} alt="" className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-muted">
          <svg width="10" height="10" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="text-muted-fg">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
      )}
    </div>
    <div className="min-w-0 flex-1">
      <p className="font-outfit font-bold text-foreground text-xs leading-tight truncate">
        {cluster.player_name ?? `#${cluster.id}`}
      </p>
      <p className="font-jakarta text-xs text-muted-fg">
        {cluster.photo_count} photo{cluster.photo_count !== 1 ? 's' : ''}
      </p>
    </div>
    {isSelected && <span className="text-accent text-xs ml-auto flex-shrink-0">▶</span>}
  </div>
);

export default ReviewPage;
