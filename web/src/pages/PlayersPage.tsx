import React, { useState, useEffect } from 'react';
import LoadingSpinner from '../components/LoadingSpinner';
import photoTaggerClient from '../api/photoTaggerClient';
import type { ClusterPlayersResult, FaceDetectionResult, PlayerCluster, PlayerPhotoItem } from '../types/index';

type ViewState = 'grid' | 'player-detail';

// Accent colors rotate per player card
const ACCENT_SHADOWS = ['shadow-pop', 'shadow-pop-pink', 'shadow-pop-yellow', 'shadow-pop-mint', 'shadow-pop-violet'];
const ACCENT_RINGS   = ['border-foreground', 'border-secondary', 'border-tertiary', 'border-quaternary', 'border-accent'];

export const PlayersPage: React.FC = () => {
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

  useEffect(() => { loadStatus(); }, []);

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
      const response = await photoTaggerClient.detectFaces();
      setDetectResult('Face detection queued…');
      const job = await photoTaggerClient.pollJob<FaceDetectionResult>(response.job_id, {
        onUpdate: currentJob => {
          if (currentJob.status === 'running') {
            setDetectResult(`Detecting faces… ${currentJob.progress}%`);
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
      setDetectResult(`Detected ${result.faces_detected} faces in ${result.photos_processed} photos${skipped}`);
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
    setSelectedPlayer(player);
    setView('player-detail');
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
    setView('grid');
    setSelectedPlayer(null);
    setPlayerPhotos([]);
    setError(null);
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
          <div>
            <h1 className="font-outfit text-4xl font-extrabold text-foreground">Player {selectedPlayer.id}</h1>
            <p className="font-jakarta text-muted-fg mt-1">
              {selectedPlayer.photo_count} photos · {selectedPlayer.face_count} appearances
            </p>
          </div>
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
            {playerPhotos.map((photo, i) => (
              <div
                key={photo.id}
                className={`sticker-card bg-white border-2 border-foreground rounded-xl ${ACCENT_SHADOWS[i % ACCENT_SHADOWS.length]} overflow-hidden`}
              >
                <div className="aspect-square bg-muted overflow-hidden relative">
                  <img
                    src={photoTaggerClient.getPhotoUrl(photo.id)}
                    alt={photo.filename}
                    className="w-full h-full object-cover"
                    onError={(e) => { e.currentTarget.style.display = 'none'; }}
                  />
                  <span className="absolute top-1.5 right-1.5 bg-foreground text-white font-jakarta text-xs font-bold px-1.5 py-0.5 rounded-full">
                    {Math.round(photo.face_confidence * 100)}%
                  </span>
                </div>
                <div className="p-2.5">
                  <p className="font-jakarta text-xs font-semibold text-foreground truncate">{photo.filename}</p>
                </div>
              </div>
            ))}
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
            <button
              onClick={handleDetect}
              disabled={isDetecting || isClustering}
              className="btn-candy w-full bg-accent text-white font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40"
            >
              {isDetecting ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Detecting… (few minutes)
                </span>
              ) : faceCount > 0 ? 'Re-detect Faces' : 'Detect Faces'}
            </button>
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

      {/* Player grid */}
      {isLoadingPlayers ? (
        <div className="flex justify-center py-12"><LoadingSpinner message="Loading players…" /></div>
      ) : players.length > 0 ? (
        <>
          <p className="font-jakarta text-sm text-muted-fg">{players.length} unique players identified</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {players.map((player, i) => (
              <button
                key={player.id}
                onClick={() => handlePlayerClick(player)}
                className={`group sticker-card bg-white border-2 border-foreground rounded-2xl ${ACCENT_SHADOWS[i % ACCENT_SHADOWS.length]} p-3 flex flex-col items-center gap-2 text-center`}
              >
                <div className={`w-20 h-20 rounded-full overflow-hidden border-2 ${ACCENT_RINGS[i % ACCENT_RINGS.length]} bg-muted`}>
                  {player.thumbnail_face_id ? (
                    <img
                      src={photoTaggerClient.getFaceCropUrl(player.thumbnail_face_id)}
                      alt={`Player ${player.id}`}
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
                </div>
                <div>
                  <p className="font-outfit font-bold text-foreground text-sm">Player {player.id}</p>
                  <p className="font-jakarta text-xs text-muted-fg">{player.photo_count} photo{player.photo_count !== 1 ? 's' : ''}</p>
                </div>
              </button>
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
    </div>
  );
};

export default PlayersPage;
