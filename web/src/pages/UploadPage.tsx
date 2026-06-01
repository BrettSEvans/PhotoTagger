import React, { useState, useEffect, useCallback, useMemo } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import PhotoUpload from '../components/PhotoUpload';
import LoadingSpinner from '../components/LoadingSpinner';
import { SidebarLayout } from '../components/SidebarLayout';
import { HierarchicalSidebar } from '../components/HierarchicalSidebar';
import { useSidebar } from '../contexts/SidebarContext';
import type { ProcessingSummary, TaggedPhoto, ReviewPhoto, PhotoBatch } from '../types/index';

type TabId = 'confirmed' | 'review';

const SHADOW_CLASSES = ['shadow-pop', 'shadow-pop-pink', 'shadow-pop-yellow', 'shadow-pop-mint', 'shadow-pop-violet'];

export const UploadPage: React.FC<{ onOpenWorkspace?: () => void; onGoToRoster?: () => void }> = ({ onOpenWorkspace, onGoToRoster }) => {
  const { setSelectedGame, clearSelection } = useSidebar();
  const [summary,       setSummary]       = useState<ProcessingSummary | null>(null);
  const [confirmedPhotos, setConfirmedPhotos] = useState<TaggedPhoto[]>([]);
  const [reviewPhotos,  setReviewPhotos]  = useState<ReviewPhoto[]>([]);
  const [activeTab,     setActiveTab]     = useState<TabId>('confirmed');
  const [isLoadingSum,  setIsLoadingSum]  = useState(true);
  const [isLoadingTab,  setIsLoadingTab]  = useState(false);
  const [batches, setBatches] = useState<PhotoBatch[]>([]);
  const [isLoadingBatches, setIsLoadingBatches] = useState(true);
  const [showPostUploadMessage, setShowPostUploadMessage] = useState(false);
  const [gameContext, setGameContext] = useState<any[]>([]);
  const [contextMsg, setContextMsg] = useState<string | null>(null);
  const [rosterTeams, setRosterTeams] = useState<string[]>([]);

  const confirmedPhotosForDisplay = useMemo(() => {
    const grouped = new Map<string, TaggedPhoto[]>();
    for (const photo of confirmedPhotos) {
      const key = `${photo.id}:${photo.jersey_number}`;
      grouped.set(key, [...(grouped.get(key) ?? []), photo]);
    }

    return Array.from(grouped.values()).flatMap(group => {
      const playerNames = new Set(group.map(photo => photo.player_name));
      return playerNames.size === 1 ? [group[0]] : [];
    });
  }, [confirmedPhotos]);

  const ambiguousConfirmedCount = confirmedPhotos.length - confirmedPhotosForDisplay.length;

  const loadSummary = useCallback(async () => {
    setIsLoadingSum(true);
    try {
      const [sum, confirmed, review] = await Promise.all([
        photoTaggerClient.getProcessingSummary(),
        photoTaggerClient.getConfirmedPhotos(),
        photoTaggerClient.getReviewPhotos(),
      ]);
      setSummary(sum);
      setConfirmedPhotos(confirmed);
      setReviewPhotos(review);
    } catch { /* summary not critical */ }
    finally { setIsLoadingSum(false); }
  }, []);

  const loadBatches = useCallback(async () => {
    setIsLoadingBatches(true);
    try {
      const data = await photoTaggerClient.getBatches();
      setBatches(data.batches || []);
    } catch { /* batches not critical */ }
    finally { setIsLoadingBatches(false); }
  }, []);

  const loadGameContext = useCallback(async () => {
    try {
      const data = await photoTaggerClient.getGameContext();
      setGameContext(data.teams.length > 0 ? data.teams : [
        { team_name: '', team_year: 0, uniform_color: '' },
        { team_name: '', team_year: 0, uniform_color: '' },
      ]);
    } catch {
      setGameContext([
        { team_name: '', team_year: 0, uniform_color: '' },
        { team_name: '', team_year: 0, uniform_color: '' },
      ]);
    }
  }, []);

  const loadRosterTeams = useCallback(async () => {
    try {
      const data = await photoTaggerClient.getRoster();
      const teams = Array.from(new Set(data.entries.map((e: any) => e.team_name))).sort();
      setRosterTeams(teams);
    } catch {
      setRosterTeams([]);
    }
  }, []);

  useEffect(() => {
    loadSummary();
    loadBatches();
    loadGameContext();
    loadRosterTeams();
  }, [loadSummary, loadBatches, loadGameContext, loadRosterTeams]);

  const handleUploadSuccess = () => {
    loadSummary();
    loadBatches();
    setShowPostUploadMessage(true);
    setTimeout(() => setShowPostUploadMessage(false), 8000);
  };

  const handleAddGame = () => {
    clearSelection();
  };

  const updateContextTeam = (index: number, patch: any) => {
    setGameContext(prev => {
      const next = [...prev];
      const current = next[index] ?? {
        team_name: '',
        team_year: 2026,
        uniform_color: '',
      };
      next[index] = {
        ...current,
        ...patch,
      };
      return next;
    });
  };

  const saveGameContext = async () => {
    setContextMsg(null);
    try {
      const teams = gameContext
        .map(team => ({
          team_name: team.team_name.trim(),
          team_year: Number(team.team_year) || 2026,
          uniform_color: team.uniform_color.trim().toLowerCase(),
        }))
        .filter(team => team.team_name && team.uniform_color);
      const data = await photoTaggerClient.setGameContext(teams);
      setGameContext(data.teams);
      setContextMsg('Game context saved');
    } catch (err) {
      console.error('Failed to save game context:', err);
    }
  };

  const switchTab = async (tab: TabId) => {
    setActiveTab(tab);
    setIsLoadingTab(true);
    try {
      if (tab === 'confirmed') {
        const photos = await photoTaggerClient.getConfirmedPhotos();
        setConfirmedPhotos(photos);
      } else {
        const photos = await photoTaggerClient.getReviewPhotos();
        setReviewPhotos(photos);
      }
    } finally { setIsLoadingTab(false); }
  };

  const confidenceColor = (c: number) => {
    if (c >= 0.7) return 'bg-quaternary';
    if (c >= 0.4) return 'bg-tertiary';
    return 'bg-secondary';
  };

  return (
    <SidebarLayout
      sidebar={
        <HierarchicalSidebar
          pageType="upload"
          batches={batches}
          onAddGame={handleAddGame}
        />
      }
      children={
        <div className="w-full py-4 space-y-6">
      {/* Page header */}
      <div>
        <h1 className="font-outfit text-4xl font-extrabold text-foreground">Upload</h1>
        <p className="mt-2 font-jakarta text-muted-fg">
          Import photos and review auto-tagging results
        </p>
      </div>

      {/* Post-upload message */}
      {showPostUploadMessage && (
        <div className="bg-quaternary/20 border-2 border-quaternary rounded-2xl shadow-pop p-5">
          <p className="font-jakarta font-semibold text-foreground mb-3">
            ✓ Photos uploaded successfully!
          </p>
          <p className="font-jakarta text-sm text-muted-fg mb-4">
            Before face matching, please upload team rosters. Set the current matchup and uniform colors below to help the AI match jersey numbers to player names.
          </p>
          {onGoToRoster && (
            <button
              onClick={onGoToRoster}
              className="btn-candy bg-quaternary text-foreground font-jakarta font-bold text-sm px-5 py-2 rounded-full border-2 border-foreground shadow-pop"
            >
              Go to Roster Page →
            </button>
          )}
        </div>
      )}

      {/* Game Context */}
      <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-mint p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="font-outfit text-lg font-bold text-foreground">Game Context (Empty on Start)</h2>
            <p className="font-jakarta text-xs text-muted-fg">Set the current matchup and uniform colors before evaluating photos</p>
          </div>
          <button
            type="button"
            onClick={saveGameContext}
            className="btn-candy bg-quaternary text-foreground font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 whitespace-nowrap"
          >
            Save Context
          </button>
        </div>
        <div className="space-y-4">
          {[0, 1].map(index => (
            <div key={index} className="space-y-2">
              <div>
                <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-2">
                  Team {index === 0 ? 'A' : 'B'}
                </label>
                {rosterTeams.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-2">
                    {rosterTeams.map(team => (
                      <button
                        key={team}
                        onClick={() => updateContextTeam(index, { team_name: team })}
                        className={`font-jakarta text-sm px-3 py-1.5 rounded-full border-2 transition-colors ${
                          gameContext[index]?.team_name === team
                            ? 'bg-accent text-white border-foreground shadow-pop'
                            : 'bg-white text-foreground border-frame hover:border-foreground'
                        }`}
                      >
                        {team}
                      </button>
                    ))}
                  </div>
                )}
                <input
                  type="text"
                  value={gameContext[index]?.team_name ?? ''}
                  onChange={e => updateContextTeam(index, { team_name: e.target.value })}
                  placeholder="Or type a team name…"
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">Year</label>
                  <input
                    type="number"
                    value={gameContext[index]?.team_year || ''}
                    placeholder="2026"
                    onChange={e => updateContextTeam(index, { team_year: Number(e.target.value) || 0 })}
                    className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
                  />
                </div>
                <div>
                  <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">Color</label>
                  <input
                    type="text"
                    value={gameContext[index]?.uniform_color ?? ''}
                    onChange={e => updateContextTeam(index, { uniform_color: e.target.value })}
                    placeholder={index === 0 ? 'red' : 'white'}
                    className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
        {contextMsg && <p className="font-jakarta text-xs font-semibold text-foreground">{contextMsg}</p>}
      </div>

      {/* Import form */}
      <PhotoUpload onUploadSuccess={handleUploadSuccess} />

      {/* ── Summary Accordion ──────────────────────────────────────────────── */}
      <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg overflow-hidden relative">
        <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-tertiary rounded-full border-2 border-foreground opacity-80" />

        {isLoadingSum ? (
          <div className="flex justify-center py-8"><LoadingSpinner message="Loading stats…" /></div>
        ) : summary ? (
          <>
            {/* Metric strip */}
            <div className="grid grid-cols-3 divide-x-2 divide-frame border-b-2 border-foreground">
              <div className="px-6 py-5 text-center">
                <p className="font-outfit text-3xl font-extrabold text-foreground">{summary.total_photos}</p>
                <p className="font-jakarta text-xs text-muted-fg mt-1 font-semibold uppercase tracking-wider">Photos</p>
              </div>
              <div className="px-6 py-5 text-center">
                <p className="font-outfit text-3xl font-extrabold text-quaternary">{summary.tagged}</p>
                <p className="font-jakarta text-xs text-muted-fg mt-1 font-semibold uppercase tracking-wider flex items-center justify-center gap-1">
                  <span>Auto-Tagged</span>
                  <svg width="12" height="12" fill="none" stroke="#34D399" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 10 10"><polyline points="1.5,5.5 4,8 8.5,2"/></svg>
                </p>
              </div>
              <div className="px-6 py-5 text-center">
                <p className="font-outfit text-3xl font-extrabold text-secondary">{summary.needs_review}</p>
                <p className="font-jakarta text-xs text-muted-fg mt-1 font-semibold uppercase tracking-wider flex items-center justify-center gap-1">
                  <span>Need Review</span>
                  <span className="text-secondary font-bold">!</span>
                </p>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex border-b-2 border-foreground">
              {([['confirmed', 'Confirmed Tags', summary.tagged], ['review', 'Needs Review', summary.needs_review]] as const).map(
                ([id, label, count]) => {
                  const displayCount = id === 'confirmed' ? confirmedPhotosForDisplay.length : count;
                  return (
                    <button
                    key={id}
                    onClick={() => switchTab(id)}
                    className={`flex-1 py-3 font-jakarta font-bold text-sm flex items-center justify-center gap-2 border-r-2 last:border-r-0 border-foreground transition-colors ${
                      activeTab === id
                        ? 'bg-foreground text-white'
                        : 'bg-white text-foreground hover:bg-muted'
                    }`}
                  >
                    {label}
                    <span className={`text-xs px-2 py-0.5 rounded-full font-bold border ${
                      activeTab === id ? 'bg-white text-foreground border-white' : 'bg-muted border-frame text-muted-fg'
                    }`}>
                      {displayCount}
                    </span>
                  </button>
                  );
                })
              }
            </div>

            {/* Tab content */}
            <div className="p-5">
              {isLoadingTab ? (
                <div className="flex justify-center py-8"><LoadingSpinner message="Loading photos…" /></div>
              ) : activeTab === 'confirmed' ? (
                confirmedPhotosForDisplay.length === 0 ? (
                  <p className="font-jakarta text-sm text-muted-fg text-center py-8">
                    No confirmed tags yet — run OCR from the Upload tab first.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {ambiguousConfirmedCount > 0 && (
                      <div className="bg-secondary/10 border-2 border-secondary rounded-xl px-4 py-3">
                        <p className="font-jakarta text-sm font-semibold text-foreground">
                          Ambiguous auto-tags hidden: {ambiguousConfirmedCount}. Set the game context and uniform colors, then rerun processing.
                        </p>
                      </div>
                    )}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                      {confirmedPhotosForDisplay.map((photo, i) => (
                        <div key={`${photo.id}:${photo.jersey_number}`} className={`sticker-card bg-white border-2 border-foreground rounded-xl ${SHADOW_CLASSES[i % SHADOW_CLASSES.length]} overflow-hidden`}>
                          <div className="aspect-square bg-muted overflow-hidden relative">
                            <img
                              src={photoTaggerClient.getPhotoUrl(photo.id)}
                              alt={photo.file_path.split('/').pop()}
                              className="w-full h-full object-cover"
                              onError={e => { e.currentTarget.style.display = 'none'; }}
                            />
                            <div className="absolute bottom-0 left-0 right-0 bg-foreground/80 px-2 py-1">
                              <p className="font-outfit font-extrabold text-white text-xs">#{photo.jersey_number}</p>
                            </div>
                          </div>
                          <div className="p-2">
                            <p className="font-jakarta text-xs font-bold text-foreground truncate">{photo.player_name}</p>
                            <div className="mt-1 flex items-center gap-1.5">
                              <div className="flex-1 h-1 bg-muted rounded-full overflow-hidden">
                                <div className={`h-full rounded-full ${confidenceColor(photo.confidence)}`} style={{ width: `${Math.min(photo.confidence * 100, 100)}%` }} />
                              </div>
                              <span className="font-jakarta text-xs text-muted-fg">{Math.round(photo.confidence * 100)}%</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              ) : (
                /* Needs Review tab */
                reviewPhotos.length === 0 ? (
                  <p className="font-jakarta text-sm text-muted-fg text-center py-8">
                    No unmatched jerseys — add more players to your roster to reduce this count.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {/* CTA */}
                    {onOpenWorkspace && (
                      <div className="flex items-center justify-between bg-secondary/10 border-2 border-secondary rounded-xl px-4 py-3">
                        <p className="font-jakarta text-sm font-semibold text-foreground">
                          {reviewPhotos.length} photos need manual jersey assignment
                        </p>
                        <button
                          onClick={onOpenWorkspace}
                          className="btn-candy bg-foreground text-white font-jakarta font-bold text-sm px-5 py-2 rounded-full border-2 border-foreground shadow-pop whitespace-nowrap"
                        >
                          Open Cleanup Workspace ({summary?.needs_review ?? reviewPhotos.length}) →
                        </button>
                      </div>
                    )}

                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                      {reviewPhotos.map((photo, i) => (
                        <div key={photo.id} className={`sticker-card bg-white border-2 border-secondary rounded-xl ${SHADOW_CLASSES[i % SHADOW_CLASSES.length]} overflow-hidden`}>
                          <div className="aspect-square bg-muted overflow-hidden relative">
                            <img
                              src={photoTaggerClient.getPhotoUrl(photo.id)}
                              alt={photo.file_path.split('/').pop()}
                              className="w-full h-full object-cover"
                              onError={e => { e.currentTarget.style.display = 'none'; }}
                            />
                            <div className="absolute top-1.5 left-1.5 bg-secondary text-white font-jakarta text-xs font-bold px-1.5 py-0.5 rounded-full">
                              #{photo.jersey_number}
                            </div>
                            <div className="absolute top-1.5 right-1.5 bg-white/90 text-secondary font-jakarta text-xs font-bold px-1.5 py-0.5 rounded-full border border-secondary">
                              !
                            </div>
                          </div>
                          <div className="p-2">
                            <p className="font-jakarta text-xs text-muted-fg truncate">{photo.file_path.split('/').pop()}</p>
                            <p className="font-jakarta text-xs text-muted-fg">{Math.round(photo.confidence * 100)}% conf.</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              )}
            </div>
          </>
        ) : (
          <div className="py-8 text-center">
            <p className="font-jakarta text-sm text-muted-fg">Run OCR to see tagging results</p>
          </div>
        )}
      </div>

      {/* ── Batches Section ────────────────────────────────────────────────── */}
      <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg overflow-hidden relative">
        <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-secondary rounded-full border-2 border-foreground opacity-80" />

        <div className="px-6 py-5 border-b-2 border-foreground">
          <h2 className="font-outfit text-lg font-bold text-foreground">Import Batches</h2>
          <p className="font-jakarta text-xs text-muted-fg mt-1">Organize and tag groups of photos by import folder</p>
        </div>

        <div className="p-5">
          {isLoadingBatches ? (
            <div className="flex justify-center py-8"><LoadingSpinner message="Loading batches…" /></div>
          ) : batches.length === 0 ? (
            <p className="font-jakarta text-sm text-muted-fg text-center py-8">No import batches yet. Photos from the upload above will appear here.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b-2 border-foreground">
                  <tr>
                    <th className="text-left px-3 py-3 font-jakarta font-bold text-muted-fg">Folder</th>
                    <th className="text-left px-3 py-3 font-jakarta font-bold text-muted-fg">Team</th>
                    <th className="text-left px-3 py-3 font-jakarta font-bold text-muted-fg">Year</th>
                    <th className="text-center px-3 py-3 font-jakarta font-bold text-muted-fg">Photos</th>
                    <th className="text-left px-3 py-3 font-jakarta font-bold text-muted-fg">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-frame">
                  {batches.map((batch) => (
                    <tr key={batch.id} className="hover:bg-muted transition-colors">
                      <td className="px-3 py-3">
                        <div className="font-jakarta font-semibold text-foreground">{batch.name || batch.source_folder.split('/').pop()}</div>
                        <div className="font-jakarta text-xs text-muted-fg truncate">{batch.source_folder}</div>
                      </td>
                      <td className="px-3 py-3 font-jakarta text-foreground">{batch.team_name || '—'}</td>
                      <td className="px-3 py-3 font-jakarta text-foreground">{batch.team_year || '—'}</td>
                      <td className="px-3 py-3 text-center font-jakarta font-semibold text-foreground">{batch.photo_count}</td>
                      <td className="px-3 py-3 font-jakarta text-muted-fg">{new Date(batch.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
        </div>
      }
    />
  );
};

export default UploadPage;
