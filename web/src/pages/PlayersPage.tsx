import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import LoadingSpinner from '../components/LoadingSpinner';
import AssignPlayerPanel, { AssignedInfo } from '../components/AssignPlayerPanel';
import photoTaggerClient from '../api/photoTaggerClient';
import { bboxStyle } from '../utils/bboxUtils';
import type { ImgDim } from '../utils/bboxUtils';
import type { ClusterPlayersResult, FaceDetectionResult, PlayerCluster, PlayerPhotoItem } from '../types/index';

type ViewState = 'grid' | 'player-detail';

// Accent colors rotate per player card
const ACCENT_SHADOWS = ['shadow-pop', 'shadow-pop-pink', 'shadow-pop-yellow', 'shadow-pop-mint', 'shadow-pop-violet'];
const ACCENT_RINGS   = ['border-foreground', 'border-secondary', 'border-tertiary', 'border-quaternary', 'border-accent'];

export const PlayersPage: React.FC = () => {
  const { clusterId } = useParams<{ clusterId?: string }>();
  const navigate = useNavigate();
  const [view, setView] = useState<ViewState>('grid');
  const [players, setPlayers] = useState<PlayerCluster[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState<PlayerCluster | null>(null);
  const [playerPhotos, setPlayerPhotos] = useState<PlayerPhotoItem[]>([]);

  const [faceCount, setFaceCount] = useState(0);
  const [clusterCount, setClusterCount] = useState(0);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);

  const [isDetecting, setIsDetecting] = useState(false);
  const [isClustering, setIsClustering] = useState(false);
  const [isLoadingPlayers, setIsLoadingPlayers] = useState(false);
  const [isLoadingPhotos, setIsLoadingPhotos] = useState(false);

  const [detectResult, setDetectResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gameContext, setGameContext] = useState<any[]>([]);

  // ── Tagging ─────────────────────────────────────────────────────────────
  const [taggingPlayer, setTaggingPlayer] = useState<PlayerCluster | null>(null);
  const [assignMsg, setAssignMsg] = useState<string | null>(null);

  // ── Face bbox overlay ────────────────────────────────────────────────────
  const [showBbox, setShowBbox] = useState(true);
  const [imgDims, setImgDims] = useState<Map<number, ImgDim>>(new Map());

  // ── HITL player matching modal ─────────────────────────────────────────
  const [matchModalPhoto, setMatchModalPhoto] = useState<PlayerPhotoItem | null>(null);
  const [isMatchingClusters, setIsMatchingClusters] = useState(false);

  const handleImgLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>, photoId: number) => {
    const img = e.currentTarget;
    setImgDims(prev => {
      const next = new Map(prev);
      next.set(photoId, { w: img.naturalWidth, h: img.naturalHeight });
      return next;
    });
  }, []);

  useEffect(() => {
    loadStatus();
    // Load game context for jersey color validation
    (async () => {
      try {
        const data = await photoTaggerClient.getGameContext();
        setGameContext(data.teams || []);
      } catch { /* non-critical */ }
    })();
  }, []);

  // Load specific player if clusterId is in the URL
  useEffect(() => {
    if (clusterId && players.length > 0) {
      const id = parseInt(clusterId, 10);
      const player = players.find(p => p.id === id);
      if (player && (!selectedPlayer || selectedPlayer.id !== id)) {
        setSelectedPlayer(player);
        setView('player-detail');
        setAssignMsg(null);
        setImgDims(new Map());
        setIsLoadingPhotos(true);
        setPlayerPhotos([]);
        (async () => {
          try {
            const result = await photoTaggerClient.getPlayerPhotos(id);
            setPlayerPhotos(result.photos);
          } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load player photos');
          } finally { setIsLoadingPhotos(false); }
        })();
      }
    }
  }, [clusterId, players]);

  /**
   * Reflect an assignment in local state: name the tagged cluster, plus any
   * clusters the similarity scan auto-tagged as the same player.
   */
  const applyAssignment = (clusterId: number, info: AssignedInfo) => {
    const autoTagged = new Set((info.matches?.auto_tagged ?? []).map(m => m.cluster_id));
    const tag = (c: PlayerCluster): PlayerCluster =>
      (c.id === clusterId || autoTagged.has(c.id))
        ? { ...c, player_name: info.playerName, jersey_number: info.jerseyNumber, roster_entry_id: info.rosterEntryId }
        : c;

    setPlayers(prev => prev.map(tag));
    setSelectedPlayer(prev => (prev ? tag(prev) : prev));

    const extra = autoTagged.size > 0 ? ` · also tagged ${autoTagged.size} more from other photos` : '';
    setAssignMsg(`Tagged as ${info.playerName} #${info.jerseyNumber}${extra}`);

    // Fire-and-forget: consolidate clusters with the same player_name
    (async () => {
      try {
        const result = await photoTaggerClient.consolidatePlayerClusters(info.playerName);
        if (result.merged && result.merged_count && result.merged_count > 0) {
          setAssignMsg(prev => (prev ? `${prev} · consolidated ${result.merged_count} duplicate cluster${result.merged_count !== 1 ? 's' : ''}` : ''));
          await loadPlayers();
        }
      } catch (err) {
        console.warn(`Failed to consolidate clusters: ${err}`);
      }
    })();
  };

  const loadStatus = async () => {
    setIsLoadingStatus(true);
    try {
      const status = await photoTaggerClient.getDetectionStatus();
      setFaceCount(status.face_count);
      setClusterCount(status.cluster_count);
      if (status.cluster_count > 0) loadPlayers();
    } catch { setError('Could not load detection status'); }
    finally { setIsLoadingStatus(false); }
  };

  const loadPlayers = async () => {
    setIsLoadingPlayers(true);
    setError(null);
    try {
      const result = await photoTaggerClient.getPlayers();
      setPlayers(result.players);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load players');
    } finally { setIsLoadingPlayers(false); }
  };

  const handleDetect = async () => {
    setIsDetecting(true);
    setDetectResult(null);
    setError(null);
    try {
      // Check game context for jersey colors
      const missingColors = gameContext.filter(team => !team.uniform_color || !team.uniform_color.trim());
      if (missingColors.length > 0) {
        const teamNames = missingColors.map(t => t.team_name || 'Unknown').join(', ');
        setError(`Jersey colors required for player matching. Missing colors for: ${teamNames}. Please fill out the Game Context card in the Upload tab.`);
        setIsDetecting(false);
        return;
      }

      const response = await photoTaggerClient.detectFaces();
      setDetectResult('Face detection and jersey recognition queued…');
      const job = await photoTaggerClient.pollJob<FaceDetectionResult>(response.job_id, {
        onUpdate: currentJob => {
          if (currentJob.status === 'running') {
            setDetectResult(`Detecting faces and reading jerseys… ${currentJob.progress}%`);
          }
        },
      });

      const result = job.result;
      if (!result) {
        throw new Error('Face detection finished without a result');
      }

      const skipped = result.photos_skipped_existing > 0
        ? ` · ${result.photos_skipped_existing} already processed`
        : '';
      const jerseyInfo = result.jersey_detections
        ? ` · ${result.jersey_detections} jerseys detected, ${result.matched_to_roster || 0} matched`
        : '';
      setDetectResult(`Detected ${result.faces_detected} faces in ${result.photos_processed} photos${jerseyInfo}${skipped}`);
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Face detection failed');
    } finally { setIsDetecting(false); }
  };

  const handleCluster = async () => {
    setIsClustering(true);
    setError(null);
    try {
      const response = await photoTaggerClient.clusterPlayers();
      const job = await photoTaggerClient.pollJob<ClusterPlayersResult>(response.job_id);
      const result = job.result;
      if (!result) {
        throw new Error('Player grouping finished without a result');
      }
      setClusterCount(result.clusters_created);
      await loadPlayers();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Clustering failed');
    } finally { setIsClustering(false); }
  };

  const handlePlayerClick = async (player: PlayerCluster) => {
    navigate(`/player/${player.id}`);
    setSelectedPlayer(player);
    setView('player-detail');
    setAssignMsg(null);
    setImgDims(new Map());
    setIsLoadingPhotos(true);
    setPlayerPhotos([]);
    try {
      const result = await photoTaggerClient.getPlayerPhotos(player.id);
      setPlayerPhotos(result.photos);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load player photos');
    } finally { setIsLoadingPhotos(false); }
  };

  const handleBack = () => {
    navigate('/players');
    setView('grid');
    setSelectedPlayer(null);
    setPlayerPhotos([]);
    setError(null);
    setAssignMsg(null);
  };

  const handleRemovePhoto = async (faceId: number, photoId: number) => {
    if (!selectedPlayer) return;
    try {
      await photoTaggerClient.removePlayerPhoto(selectedPlayer.id, faceId);
      setPlayerPhotos(prev => prev.filter(p => p.id !== photoId));
      setAssignMsg(`Removed photo from ${selectedPlayer.player_name || `Player ${selectedPlayer.id}`}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove photo');
    }
  };

  const handleMatchOtherClusters = async () => {
    if (!matchModalPhoto) return;
    setIsMatchingClusters(true);
    setError(null);
    try {
      const result = await photoTaggerClient.matchSimilarClusters(selectedPlayer?.id || 0);

      const autoCount = result.auto_tagged?.length || 0;
      const suggestedCount = result.suggestions?.length || 0;

      if (autoCount > 0) {
        setAssignMsg(`Auto-matched ${autoCount} face${autoCount !== 1 ? 's' : ''} to player stack${autoCount !== 1 ? 's' : ''}`);
        await loadPlayers();
      } else if (suggestedCount > 0) {
        setAssignMsg(`Found ${suggestedCount} potential match${suggestedCount !== 1 ? 'es' : ''} — review in player grid`);
      } else {
        setAssignMsg('No other matching player stacks found');
      }

      setMatchModalPhoto(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to match clusters');
    } finally {
      setIsMatchingClusters(false);
    }
  };

  if (isLoadingStatus) {
    return <div className="flex justify-center py-16"><LoadingSpinner message="Loading player data…" /></div>;
  }

  // ── Player Detail ───────────────────────────────────────────────────────────
  if (view === 'player-detail' && selectedPlayer) {
    return (
      <div className="w-full max-w-6xl mx-auto py-4 space-y-6">
        <button
          onClick={handleBack}
          className="btn-candy flex items-center gap-2 font-jakarta font-bold text-sm text-foreground bg-white border-2 border-foreground rounded-full px-4 py-2 shadow-pop hover:bg-tertiary"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          All Players
        </button>

        <div className="flex items-center gap-4">
          {selectedPlayer.thumbnail_face_id && (
            <div className="w-20 h-20 rounded-full overflow-hidden border-2 border-foreground shadow-pop flex-shrink-0">
              <img
                src={photoTaggerClient.getFaceCropUrl(selectedPlayer.thumbnail_face_id)}
                alt="Player"
                className="w-full h-full object-cover"
                onError={(e) => { e.currentTarget.style.display = 'none'; }}
              />
            </div>
          )}
          <div className="flex-1">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="font-outfit text-4xl font-extrabold text-foreground">
                {selectedPlayer.player_name || `Player ${selectedPlayer.id}`}
                {selectedPlayer.jersey_number && (
                  <span className="ml-3 align-middle text-2xl text-accent">#{selectedPlayer.jersey_number}</span>
                )}
              </h1>
              <button
                type="button"
                onClick={() => setShowBbox(v => !v)}
                title={showBbox ? 'Hide face box' : 'Show face box'}
                className={`flex items-center gap-1.5 font-jakarta font-bold text-xs px-3 py-1.5 rounded-full border-2 transition-colors ${
                  showBbox
                    ? 'bg-accent text-white border-foreground shadow-pop'
                    : 'bg-white text-foreground border-frame hover:border-foreground'
                }`}
              >
                {/* face-box icon: square with a small circle inside */}
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="1" y="1" width="12" height="12" rx="1.5" />
                  <circle cx="7" cy="7" r="2.2" />
                </svg>
                {showBbox ? 'Face on' : 'Face off'}
              </button>
            </div>
            <p className="font-jakarta text-muted-fg mt-1">
              {selectedPlayer.photo_count} photos · {selectedPlayer.face_count} appearances
            </p>
          </div>
        </div>

        {/* Inline tagging — reuses the shared assign + match-similar workflow */}
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop p-4 space-y-2">
          <p className="font-outfit font-bold text-foreground text-sm">
            {selectedPlayer.player_name ? 'Re-tag this player' : 'Tag this player'}
          </p>
          <AssignPlayerPanel
            clusterId={selectedPlayer.id}
            onAssigned={(info) => applyAssignment(selectedPlayer.id, info)}
          />
          {assignMsg && (
            <p role="status" className="font-jakarta text-xs text-foreground bg-quaternary/20 rounded-lg px-2 py-1">✅ {assignMsg}</p>
          )}
        </div>

        {error && (
          <div role="alert" aria-live="assertive" className="bg-white border-2 border-secondary rounded-xl shadow-pop-pink p-4">
            <p className="font-jakarta text-sm text-foreground">⚠️ {error}</p>
          </div>
        )}

        {isLoadingPhotos ? (
          <div className="flex justify-center py-12"><LoadingSpinner message="Loading photos…" /></div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {playerPhotos.map((photo, i) => {
              const dim = imgDims.get(photo.id);
              return (
                <div
                  key={photo.id}
                  className={`sticker-card bg-white border-2 border-foreground rounded-xl ${ACCENT_SHADOWS[i % ACCENT_SHADOWS.length]} overflow-hidden group`}
                >
                  <div className="aspect-square bg-muted overflow-hidden relative">
                    <img
                      src={photoTaggerClient.getPhotoUrl(photo.id)}
                      alt={photo.filename}
                      className="w-full h-full object-cover"
                      onLoad={(e) => handleImgLoad(e, photo.id)}
                      onError={(e) => { e.currentTarget.style.display = 'none'; }}
                    />
                    {/* Purple face bbox overlay */}
                    {showBbox && dim && photo.face_bbox && (
                      <div
                        className="absolute border-2 border-accent pointer-events-none rounded-sm"
                        style={bboxStyle(photo.face_bbox, dim, 4)}
                      />
                    )}
                    <span className="absolute top-1.5 right-1.5 bg-foreground text-white font-jakarta text-xs font-bold px-1.5 py-0.5 rounded-full">
                      {Math.round(photo.face_confidence * 100)}%
                    </span>
                    {/* Action buttons — appear on hover */}
                    <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity flex items-end gap-1.5 p-1.5 bg-gradient-to-b from-transparent via-transparent to-foreground/10 pointer-events-auto">
                      <button
                        onClick={() => setMatchModalPhoto(photo)}
                        className="flex-1 bg-accent text-white text-[10px] font-jakarta font-bold rounded-lg px-1.5 py-1 hover:bg-accent/90"
                        title="Match other faces in this photo to other players"
                      >
                        Match others
                      </button>
                      <button
                        onClick={() => handleRemovePhoto(photo.face_id, photo.id)}
                        className="bg-secondary text-white rounded-full w-5 h-5 flex items-center justify-center font-jakarta font-bold text-xs hover:bg-secondary/80"
                        title="Remove photo from this player"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                  <div className="p-2.5">
                    <p className="font-jakarta text-xs font-semibold text-foreground truncate">{photo.filename}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* HITL Cluster Matching Modal */}
        {matchModalPhoto && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
            role="dialog"
            aria-modal="true"
            onClick={() => !isMatchingClusters && setMatchModalPhoto(null)}
          >
            <div
              className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg w-full max-w-md p-6 space-y-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 bg-accent rounded-lg border-2 border-foreground flex items-center justify-center flex-shrink-0">
                  <svg width="16" height="16" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                    <path d="M12 8v4M12 16h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="font-outfit font-bold text-foreground">
                    Match other players?
                  </h3>
                  <p className="font-jakarta text-xs text-muted-fg mt-1">
                    This photo may contain faces of other players. Would you like to auto-match them to their correct player clusters?
                  </p>
                </div>
                <button
                  onClick={() => setMatchModalPhoto(null)}
                  disabled={isMatchingClusters}
                  aria-label="Close"
                  className="text-muted-fg hover:text-foreground text-xl leading-none px-1 disabled:cursor-not-allowed"
                >
                  ×
                </button>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => setMatchModalPhoto(null)}
                  disabled={isMatchingClusters}
                  className="flex-1 font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground bg-white text-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Skip
                </button>
                <button
                  onClick={handleMatchOtherClusters}
                  disabled={isMatchingClusters}
                  className="flex-1 font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground bg-accent text-white hover:bg-accent/90 shadow-pop disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isMatchingClusters ? (
                    <>
                      <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Matching…
                    </>
                  ) : (
                    'Yes, match them'
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── Players Grid ────────────────────────────────────────────────────────────
  return (
    <div className="w-full max-w-6xl mx-auto py-4 space-y-6">
      <div>
        <h1 className="font-outfit text-4xl font-extrabold text-foreground">Players</h1>
        <p className="mt-2 font-jakarta text-muted-fg">Faces grouped by identity across all photos</p>
      </div>

      {/* Pipeline steps */}
      <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg p-6 space-y-4 relative overflow-hidden">
        <div aria-hidden="true" className="absolute -top-4 -right-4 w-12 h-12 bg-secondary rounded-full border-2 border-foreground opacity-70" />
        <div aria-hidden="true" className="absolute bottom-3 right-8 w-6 h-6 bg-quaternary rotate-45 border-2 border-foreground opacity-60" />

        <h2 className="font-outfit text-lg font-bold text-foreground">Detection Pipeline</h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Step 1 */}
          <div className="border-2 border-frame rounded-xl p-4 space-y-3 relative">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-6 h-6 bg-accent rounded-full border-2 border-foreground flex items-center justify-center">
                    <span className="text-white font-outfit font-bold text-xs">1</span>
                  </div>
                  <p className="font-outfit font-bold text-foreground">Detect Faces</p>
                </div>
                <p className="font-jakarta text-xs text-muted-fg pl-8">
                  {faceCount > 0 ? `${faceCount} faces stored` : 'No faces detected yet'}
                </p>
              </div>
              {faceCount > 0 && (
                <div className="w-6 h-6 bg-quaternary rounded-full border-2 border-foreground flex items-center justify-center">
                  <svg width="10" height="10" fill="none" stroke="#1E293B" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 10 10" aria-hidden="true">
                    <polyline points="1.5,5.5 4,8 8.5,2" />
                  </svg>
                </div>
              )}
            </div>
            {(() => {
              const missingColors = gameContext.filter(team => !team.uniform_color || !team.uniform_color.trim());
              const isDisabled = isDetecting || isClustering || missingColors.length > 0;
              const tooltipText = missingColors.length > 0
                ? `Jersey colors required: ${missingColors.map(t => t.team_name || 'Unknown').join(', ')}. Fill out Game Context in Upload tab.`
                : '';
              return (
                <button
                  onClick={handleDetect}
                  disabled={isDisabled}
                  title={tooltipText}
                  className="btn-candy w-full bg-accent text-white font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isDetecting ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Detecting… (few minutes)
                    </span>
                  ) : faceCount > 0 ? 'Re-detect Faces' : 'Detect Faces'}
                </button>
              );
            })()}
            {detectResult && (
              <p className="font-jakarta text-xs text-foreground bg-quaternary/20 rounded-lg px-2 py-1">✅ {detectResult}</p>
            )}
          </div>

          {/* Step 2 */}
          <div className="border-2 border-frame rounded-xl p-4 space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-6 h-6 bg-secondary rounded-full border-2 border-foreground flex items-center justify-center">
                    <span className="text-white font-outfit font-bold text-xs">2</span>
                  </div>
                  <p className="font-outfit font-bold text-foreground">Group Players</p>
                </div>
                <p className="font-jakarta text-xs text-muted-fg pl-8">
                  {clusterCount > 0 ? `${clusterCount} players identified` : 'Not grouped yet'}
                </p>
              </div>
              {clusterCount > 0 && (
                <div className="w-6 h-6 bg-quaternary rounded-full border-2 border-foreground flex items-center justify-center">
                  <svg width="10" height="10" fill="none" stroke="#1E293B" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 10 10" aria-hidden="true">
                    <polyline points="1.5,5.5 4,8 8.5,2" />
                  </svg>
                </div>
              )}
            </div>
            <button
              onClick={handleCluster}
              disabled={faceCount === 0 || isDetecting || isClustering}
              className="btn-candy w-full bg-secondary text-foreground font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground shadow-pop-pink disabled:opacity-40"
            >
              {isClustering ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-foreground border-t-transparent rounded-full animate-spin" />
                  Grouping…
                </span>
              ) : clusterCount > 0 ? 'Re-group Players' : 'Group Players'}
            </button>

            {faceCount === 0 && (
              <p className="font-jakarta text-xs text-muted-fg">Run face detection first</p>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" aria-live="assertive" className="bg-white border-2 border-secondary rounded-xl shadow-pop-pink p-4 flex items-center justify-between">
          <p className="font-jakarta text-sm text-foreground">⚠️ {error}</p>
          <button onClick={() => setError(null)} className="font-jakarta text-xs text-muted-fg hover:text-foreground underline">Dismiss</button>
        </div>
      )}

      {assignMsg && !taggingPlayer && (
        <div role="status" aria-live="polite" className="bg-quaternary/10 border-2 border-quaternary rounded-xl p-4 flex items-center justify-between">
          <p className="font-jakarta text-sm font-medium text-foreground">✅ {assignMsg}</p>
          <button onClick={() => setAssignMsg(null)} className="font-jakarta text-xs text-muted-fg hover:text-foreground underline">Dismiss</button>
        </div>
      )}

      {/* Player grid */}
      {isLoadingPlayers ? (
        <div className="flex justify-center py-12"><LoadingSpinner message="Loading players…" /></div>
      ) : players.length > 0 ? (
        <>
          <p className="font-jakarta text-sm text-muted-fg">{players.length} unique players identified</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {players.map((player, i) => (
              <div
                key={player.id}
                className={`group sticker-card bg-white border-2 border-foreground rounded-2xl ${ACCENT_SHADOWS[i % ACCENT_SHADOWS.length]} p-3 flex flex-col items-center gap-2 text-center`}
              >
                <button
                  onClick={() => handlePlayerClick(player)}
                  className="flex flex-col items-center gap-2 w-full"
                >
                  <div className={`relative w-20 h-20 rounded-full overflow-hidden border-2 ${ACCENT_RINGS[i % ACCENT_RINGS.length]} bg-muted`}>
                    {player.thumbnail_face_id ? (
                      <img
                        src={photoTaggerClient.getFaceCropUrl(player.thumbnail_face_id)}
                        alt={player.player_name || `Player ${player.id}`}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                          const p = e.currentTarget.parentElement;
                          if (p) p.innerHTML = `<div class="w-full h-full flex items-center justify-center"><svg class="w-5 h-5 text-muted-fg" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg></div>`;
                        }}
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-muted-fg">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      </div>
                    )}
                    {player.jersey_number && (
                      <span className="absolute -bottom-0.5 -right-0.5 bg-accent text-white font-jakarta text-[10px] font-bold px-1.5 py-0.5 rounded-full border-2 border-foreground">
                        #{player.jersey_number}
                      </span>
                    )}
                  </div>
                  <div>
                    <p className="font-outfit font-bold text-foreground text-sm truncate max-w-[8rem]">
                      {player.player_name || `Player ${player.id}`}
                    </p>
                    <p className="font-jakarta text-xs text-muted-fg">{player.photo_count} photo{player.photo_count !== 1 ? 's' : ''}</p>
                  </div>
                </button>
                <button
                  onClick={() => { setTaggingPlayer(player); setAssignMsg(null); }}
                  className="btn-candy w-full bg-tertiary text-white font-jakarta font-bold text-xs px-3 py-1.5 rounded-full border-2 border-foreground shadow-pop hover:opacity-90"
                >
                  {player.player_name ? '✎ Re-tag' : '+ Tag'}
                </button>
              </div>
            ))}
          </div>
        </>
      ) : clusterCount === 0 && faceCount === 0 ? (
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg p-14 text-center relative overflow-hidden">
          <div aria-hidden="true" className="absolute -top-5 -right-5 w-14 h-14 bg-secondary rounded-full border-2 border-foreground opacity-70" />
          <div aria-hidden="true" className="absolute bottom-4 left-6 w-8 h-8 bg-tertiary rotate-12 border-2 border-foreground opacity-60" />
          <div className="w-10 h-10 bg-muted rounded-xl border-2 border-foreground mx-auto flex items-center justify-center mb-4">
            <svg className="w-5 h-5 text-muted-fg" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <h3 className="font-outfit text-xl font-bold text-foreground">No players yet</h3>
          <p className="mt-2 font-jakarta text-muted-fg max-w-xs mx-auto">
            Run Detect Faces, then Group Players to see who's in your photos
          </p>
        </div>
      ) : null}

      {/* Tag modal — same assign + match-similar workflow as the detail page */}
      {taggingPlayer && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => setTaggingPlayer(null)}
        >
          <div
            className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg w-full max-w-md p-5 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              {taggingPlayer.thumbnail_face_id && (
                <div className="w-12 h-12 rounded-full overflow-hidden border-2 border-foreground flex-shrink-0">
                  <img
                    src={photoTaggerClient.getFaceCropUrl(taggingPlayer.thumbnail_face_id)}
                    alt=""
                    className="w-full h-full object-cover"
                    onError={(e) => { e.currentTarget.style.display = 'none'; }}
                  />
                </div>
              )}
              <div className="flex-1">
                <h3 className="font-outfit font-bold text-foreground">
                  {taggingPlayer.player_name ? 'Re-tag player' : 'Tag player'}
                </h3>
                <p className="font-jakarta text-xs text-muted-fg">
                  {taggingPlayer.player_name || `Player ${taggingPlayer.id}`} · {taggingPlayer.photo_count} photos
                </p>
              </div>
              <button
                onClick={() => setTaggingPlayer(null)}
                aria-label="Close"
                className="text-muted-fg hover:text-foreground text-xl leading-none px-1"
              >
                ×
              </button>
            </div>

            <AssignPlayerPanel
              clusterId={taggingPlayer.id}
              autoFocus
              onAssigned={(info) => {
                applyAssignment(taggingPlayer.id, info);
                setTaggingPlayer(null);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default PlayersPage;
