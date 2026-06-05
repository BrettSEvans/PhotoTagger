import React, { useState, useEffect, useCallback, useMemo } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import SelectPhotosCard, { type UploadMode } from '../components/SelectPhotosCard';
import LoadingSpinner from '../components/LoadingSpinner';
import { SidebarLayout } from '../components/SidebarLayout';
import { HierarchicalSidebar } from '../components/HierarchicalSidebar';
import { useSidebar } from '../contexts/SidebarContext';
import type { ProcessingSummary, TaggedPhoto, ReviewPhoto, PhotoBatch, CrawlResult } from '../types/index';

type TabId = 'confirmed' | 'review';

const SHADOW_CLASSES = ['shadow-pop', 'shadow-pop-pink', 'shadow-pop-yellow', 'shadow-pop-mint', 'shadow-pop-violet'];

export const UploadPage: React.FC<{ onOpenWorkspace?: () => void; onGoToRoster?: () => void }> = ({ onOpenWorkspace, onGoToRoster }) => {
  const { selectedGame, selectedTournament, selectedYear, setSelectedGame, clearSelection } = useSidebar();
  const [summary,       setSummary]       = useState<ProcessingSummary | null>(null);
  const [confirmedPhotos, setConfirmedPhotos] = useState<TaggedPhoto[]>([]);
  const [reviewPhotos,  setReviewPhotos]  = useState<ReviewPhoto[]>([]);
  const [activeTab,     setActiveTab]     = useState<TabId>('confirmed');
  const [isLoadingSum,  setIsLoadingSum]  = useState(true);
  const [isLoadingTab,  setIsLoadingTab]  = useState(false);
  const [batches, setBatches] = useState<PhotoBatch[]>([]);
  const [isLoadingBatches, setIsLoadingBatches] = useState(true);
  const [showPostUploadMessage, setShowPostUploadMessage] = useState(false);
  const [gameContext, setGameContext] = useState<any[]>([
    { team_name: '', team_year: 0, uniform_color: '' },
    { team_name: '', team_year: 0, uniform_color: '' },
  ]);
  const [tournament, setTournament] = useState('');
  const [tournamentInput, setTournamentInput] = useState('');
  const [showTournamentDropdown, setShowTournamentDropdown] = useState(false);
  const [contextMsg, setContextMsg] = useState<string | null>(null);
  const [rosterTeams, setRosterTeams] = useState<string[]>([]);
  const [rosterTeamYears, setRosterTeamYears] = useState<Record<string, number>>({});

  // Photo selection state (lifted from PhotoUpload)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [photoDirectory, setPhotoDirectory] = useState('');
  const [uploadMode, setUploadMode] = useState<UploadMode>('files');
  const [isDragging, setIsDragging] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [isSavingGame, setIsSavingGame] = useState(false);

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
      if (data.teams.length > 0) {
        setGameContext(data.teams.map((t: any) => ({ team_name: t.team_name, team_year: t.team_year, uniform_color: t.uniform_color ?? '' })));
      }
    } catch { /* non-critical */ }
  }, []);

  const loadRosterTeams = useCallback(async () => {
    try {
      const data = await photoTaggerClient.getRoster();
      const teams = Array.from(new Set(data.entries.map((e: any) => e.team_name))).sort() as string[];
      setRosterTeams(teams);
      // Build team → most-recent year map
      const yearMap: Record<string, number> = {};
      data.entries.forEach((e: any) => {
        if (!yearMap[e.team_name] || e.team_year > yearMap[e.team_name]) {
          yearMap[e.team_name] = e.team_year;
        }
      });
      setRosterTeamYears(yearMap);
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

  // When a game is selected from the sidebar, populate the Game Details form
  useEffect(() => {
    if (!selectedGame || batches.length === 0) return;

    // Find the batch that matches the selected game
    const selectedBatch = batches.find(b => b.source_folder === selectedGame || b.id.toString() === selectedGame);
    if (!selectedBatch) return;

    // Parse the game name to extract Team A and Team B
    // Game name format is typically "Team A vs Team B"
    const teamA = selectedBatch.team_name || '';
    let teamB = '';

    if (selectedBatch.name) {
      const vsIndex = selectedBatch.name.indexOf(' vs ');
      if (vsIndex > -1) {
        teamB = selectedBatch.name.substring(vsIndex + 4).trim();
      }
    }

    // Populate the form
    setTournament(selectedBatch.tournament || '');
    setTournamentInput(selectedBatch.tournament || '');
    setGameContext([
      {
        team_name: teamA,
        team_year: selectedBatch.team_year || 0,
        uniform_color: '',
      },
      {
        team_name: teamB,
        team_year: selectedBatch.team_year || 0,
        uniform_color: '',
      },
    ]);
  }, [selectedGame, batches]);

  const handleUploadSuccess = () => {
    loadSummary();
    loadBatches();
    setShowPostUploadMessage(true);
    setTimeout(() => setShowPostUploadMessage(false), 8000);
  };

  const handleAddGame = () => {
    clearSelection();
  };

  /** Select a roster team for a slot; year auto-fills from roster. */
  const selectContextTeam = (index: number, teamName: string) => {
    const year = rosterTeamYears[teamName] ?? 0;
    setGameContext(prev => {
      const next = [...prev];
      next[index] = { team_name: teamName, team_year: year, uniform_color: '' };
      return next;
    });
  };

  const updateContextTeam = (index: number, patch: any) => {
    setGameContext(prev => {
      const next = [...prev];
      next[index] = { ...(next[index] ?? { team_name: '', team_year: 0, uniform_color: '' }), ...patch };
      return next;
    });
  };

  const saveGameContext = async () => {
    setContextMsg(null);
    try {
      const teams = gameContext
        .map(team => ({
          team_name: (team.team_name ?? '').trim(),
          team_year: Number(team.team_year) || new Date().getFullYear(),
          uniform_color: (team.uniform_color ?? '').trim(),
        }))
        .filter(team => team.team_name);
      await photoTaggerClient.setGameContext(teams);
      setContextMsg('Game saved');

      // Tag the most recently uploaded batch with tournament + team info so the
      // sidebar hierarchy populates immediately.
      if (batches.length > 0) {
        const latestBatch = batches.reduce((a, b) => (b.id > a.id ? b : a));
        const teamA = teams[0];
        const teamB = teams[1];
        const gameName = teamB
          ? `${teamA.team_name} vs ${teamB.team_name}`
          : teamA.team_name;

        await photoTaggerClient.updateBatch(latestBatch.id, {
          tournament: tournament.trim() || undefined,
          team_name: teamA?.team_name || undefined,
          team_year: teamA?.team_year,
          name: gameName,
        });
      }

      await loadBatches();
    } catch (err) {
      console.error('Failed to save game context:', err);
      setContextMsg('Save failed');
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

  // Drag and drop handlers for file selection
  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    const imageFiles = files.filter(file => file.type.startsWith('image/'));

    if (imageFiles.length === 0) {
      setUploadMessage({
        type: 'error',
        text: 'Please drop image files only (JPG, PNG, TIFF, HEIC, WebP)',
      });
      return;
    }

    setSelectedFiles(imageFiles);
    setUploadMessage(null);
  };

  // Unified handler: save game + upload photos
  const handleSaveGameAndUpload = async () => {
    if (selectedFiles.length === 0) {
      setUploadMessage({ type: 'error', text: 'Please select at least one photo' });
      return;
    }

    if (!gameContext[0]?.team_name) {
      setUploadMessage({ type: 'error', text: 'Please enter Team A name' });
      return;
    }

    setIsSavingGame(true);
    try {
      // 1. Save game context first
      setContextMsg(null);
      const teams = gameContext
        .map(team => ({
          team_name: (team.team_name ?? '').trim(),
          team_year: Number(team.team_year) || new Date().getFullYear(),
          uniform_color: (team.uniform_color ?? '').trim(),
        }))
        .filter(team => team.team_name);

      await photoTaggerClient.setGameContext(teams);

      // Update batch with game name
      if (batches.length > 0) {
        const latestBatch = batches.reduce((a, b) => (b.id > a.id ? b : a));
        const teamA = teams[0];
        const teamB = teams[1];
        const gameName = teamB
          ? `${teamA.team_name} vs ${teamB.team_name}`
          : teamA.team_name;

        await photoTaggerClient.updateBatch(latestBatch.id, {
          tournament: tournament.trim() || undefined,
          team_name: teamA?.team_name || undefined,
          team_year: teamA?.team_year,
          name: gameName,
        });
      }

      await loadBatches();
      setContextMsg('Game saved');

      // 2. Upload photos
      setUploadMessage(null);
      const formData = new FormData();
      selectedFiles.forEach(file => formData.append('files', file));

      const response = await photoTaggerClient.uploadPhotos(formData);

      // Poll job status
      const job = await photoTaggerClient.pollJob<CrawlResult>(response.job_id, {
        onUpdate: currentJob => {
          if (currentJob.status === 'queued') {
            setUploadMessage({ type: 'success', text: 'Processing queued…' });
          } else if (currentJob.status === 'running') {
            setUploadMessage({ type: 'success', text: `Processing… ${currentJob.progress}%` });
          }
        },
      });

      const result = job.result as CrawlResult;
      if (!result) {
        throw new Error('Upload finished without a result');
      }

      // 3. Show success and clear
      setUploadMessage({
        type: 'success',
        text: `Added ${result.photos_ingested} photos · ${result.duplicates_skipped} duplicates skipped`,
      });
      setSelectedFiles([]);
      setPhotoDirectory('');
      setShowPostUploadMessage(true);
      setTimeout(() => setShowPostUploadMessage(false), 8000);
      await loadSummary();
      await loadBatches();
    } catch (error) {
      console.error('Failed to save game and upload photos:', error);
      setUploadMessage({
        type: 'error',
        text: error instanceof Error ? error.message : 'Failed to save game and upload photos',
      });
    } finally {
      setIsSavingGame(false);
    }
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

      {/* ── Step 1: Select Photos ────────────────────────────────────────────── */}
      <SelectPhotosCard
        selectedFiles={selectedFiles}
        uploadMode={uploadMode}
        photoDirectory={photoDirectory}
        isDragging={isDragging}
        message={uploadMessage}
        isLoading={isSavingGame}
        onFilesSelected={setSelectedFiles}
        onModeChange={setUploadMode}
        onDirectoryChange={setPhotoDirectory}
        onClear={() => {
          setSelectedFiles([]);
          setUploadMessage(null);
        }}
        onError={(msg) => setUploadMessage({ type: 'error', text: msg })}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      />

      {/* ── Game Context ────────────────────────────────────────────────────── */}
      {(() => {
        const existingTournaments = [...new Set(batches.map(b => b.tournament).filter(Boolean))] as string[];
        const filteredTournaments = tournamentInput.trim()
          ? existingTournaments.filter(t => t.toLowerCase().includes(tournamentInput.toLowerCase()))
          : existingTournaments;
        return (
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-mint p-5 space-y-4 relative overflow-hidden">
          <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-quaternary rounded-full border-2 border-foreground opacity-80" />
          <div className="flex items-center gap-2">
            <span className="font-outfit text-lg font-bold text-foreground">2.</span>
            <h2 className="font-outfit text-lg font-bold text-foreground">Game Details</h2>
          </div>

          {/* Tournament typeahead */}
          <div className="relative">
            <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">Tournament</label>
            <input
              type="text"
              value={tournamentInput}
              onChange={e => { setTournamentInput(e.target.value); setTournament(e.target.value); setShowTournamentDropdown(true); }}
              onFocus={() => setShowTournamentDropdown(true)}
              onBlur={() => setTimeout(() => setShowTournamentDropdown(false), 150)}
              className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
            />
            {showTournamentDropdown && filteredTournaments.length > 0 && (
              <ul className="absolute z-20 left-0 right-0 mt-1 bg-white border-2 border-foreground rounded-xl shadow-pop overflow-hidden max-h-40 overflow-y-auto">
                {filteredTournaments.map(t => (
                  <li key={t}>
                    <button
                      type="button"
                      onMouseDown={() => { setTournamentInput(t); setTournament(t); setShowTournamentDropdown(false); }}
                      className="w-full text-left px-3 py-2 font-jakarta text-sm hover:bg-quaternary/10"
                    >
                      {t}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Team A / Team B */}
          <div className="grid grid-cols-2 gap-4">
            {[0, 1].map(index => (
              <div key={index} className="space-y-2">
                <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground">
                  Team {index === 0 ? 'A' : 'B'}
                </label>
                <select
                  value={gameContext[index]?.team_name || ''}
                  onChange={e => {
                    if (e.target.value) {
                      selectContextTeam(index, e.target.value);
                    } else {
                      updateContextTeam(index, { team_name: '', team_year: 0, uniform_color: '' });
                    }
                  }}
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                >
                  <option value="">— Select Team —</option>
                  {rosterTeams.map(team => (
                    <option key={team} value={team}>
                      {team}
                    </option>
                  ))}
                </select>
                {gameContext[index]?.team_name && (
                  <>
                    <p className="font-jakarta text-xs text-muted-fg">
                      {gameContext[index].team_name}
                      {gameContext[index].team_year ? ` · ${gameContext[index].team_year}` : ''}
                    </p>
                    <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground">
                      Jersey Color
                    </label>
                    <input
                      type="text"
                      value={gameContext[index].uniform_color ?? ''}
                      onChange={e => updateContextTeam(index, { uniform_color: e.target.value })}
                      className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                    />
                  </>
                )}
              </div>
            ))}
          </div>

          {contextMsg && (
            <p className={`font-jakarta text-xs font-semibold ${contextMsg === 'Save failed' ? 'text-secondary' : 'text-foreground'}`}>
              {contextMsg === 'Game saved' ? '✅ ' : '⚠️ '}{contextMsg}
            </p>
          )}
        </div>
        );
      })()}

      {/* ── Step 3: Unified CTA ──────────────────────────────────────────── */}
      <div className="flex gap-3 items-center">
        <span className="font-outfit text-lg font-bold text-foreground">3.</span>
        <button
          onClick={handleSaveGameAndUpload}
          disabled={isSavingGame || selectedFiles.length === 0 || !gameContext[0]?.team_name}
          className="flex-1 btn-candy bg-accent text-white font-jakarta font-bold px-6 py-4 rounded-full border-2 border-foreground shadow-pop disabled:opacity-50 disabled:cursor-not-allowed text-lg"
        >
          {isSavingGame ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Saving game & uploading…
            </span>
          ) : 'Save game & upload photos'}
        </button>
      </div>

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
