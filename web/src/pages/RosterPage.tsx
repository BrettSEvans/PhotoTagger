import React, { useState, useEffect, useRef, useMemo } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from '../components/LoadingSpinner';
import { SidebarLayout } from '../components/SidebarLayout';
import { HierarchicalSidebar } from '../components/HierarchicalSidebar';
import { useSidebar } from '../contexts/SidebarContext';
import type { GameContextTeam, RosterEntry } from '../types/index';

export const RosterPage: React.FC = () => {
  const { selectedYear, selectedTeam } = useSidebar();
  const [entries, setEntries]       = useState<RosterEntry[]>([]);
  const [isLoading, setIsLoading]   = useState(true);
  const [error, setError]           = useState<string | null>(null);

  // Inline entry form
  const [newName,   setNewName]   = useState('');
  const [newJersey, setNewJersey] = useState('');
  const [newTeam,   setNewTeam]   = useState('');
  const [teamYear,  setTeamYear]  = useState(2026);
  const [teamColor, setTeamColor] = useState('');
  const [isSaving,  setIsSaving]  = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const rosterUrlRef = useRef<HTMLInputElement>(null);
  const importCardRef = useRef<HTMLDivElement>(null);

  const [gameContext, setGameContext] = useState<GameContextTeam[]>([]);
  const [contextMsg, setContextMsg] = useState<string | null>(null);

  // Reset all data
  const [isResetting,  setIsResetting]  = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  // Bulk import state
  const [isDragging, setIsDragging] = useState(false);
  const [isParsing,  setIsParsing]  = useState(false);
  const [importMsg,  setImportMsg]  = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [rosterUrl,  setRosterUrl]  = useState('');
  const [importTeam, setImportTeam] = useState('');
  const [importTeamYear,   setImportTeamYear]   = useState(2026);
  const [duplicatePolicy, setDuplicatePolicy] = useState<'replace' | 'skip'>('replace');
  // Whether to show the "Import as team" pill row — hidden after +Add Roster is pressed
  const [showImportTeamPills, setShowImportTeamPills] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Individual player edit modal state
  const [editingEntry, setEditingEntry] = useState<RosterEntry | null>(null);
  const [editForm, setEditForm] = useState({
    player_name: '',
    jersey_number: '',
    team_name: '',
    team_year: 2026,
    uniform_color: '',
  });
  const [editError, setEditError] = useState<string | null>(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // Bulk roster edit modal state
  const [showBulkEditModal, setShowBulkEditModal] = useState(false);
  const [bulkEditForm, setBulkEditForm] = useState({ team_name: '', team_year: 2026 });
  const [bulkEditError, setBulkEditError] = useState<string | null>(null);
  const [isSavingBulk, setIsSavingBulk] = useState(false);

  // Derived team list for filtering
  const rosterTeams = useMemo(() => {
    const teams = new Set<string>();
    entries.forEach(e => {
      if (e.team_name) teams.add(e.team_name);
    });
    return Array.from(teams).sort();
  }, [entries]);

  const allTeamOptions = useMemo(() => {
    return ['All Teams', ...rosterTeams];
  }, [rosterTeams]);

  useEffect(() => {
    loadRoster();
    loadGameContext();
  }, []);

  const loadRoster = async () => {
    setIsLoading(true);
    try {
      const data = await photoTaggerClient.getRoster();
      setEntries(data.entries);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load roster');
    } finally {
      setIsLoading(false);
    }
  };

  const loadGameContext = async () => {
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
  };

  const clearAllForms = () => {
    // Clear player entry form
    setNewName('');
    setNewJersey('');
    setNewTeam('');
    setTeamYear(2026);
    setTeamColor('');

    // Clear import form — team and year blanked so user starts fresh
    setRosterUrl('');
    setImportTeam('');
    setImportTeamYear(2026);
    setDuplicatePolicy('replace');
    // Hide team pills until user interacts with the import form again
    setShowImportTeamPills(false);
    setImportMsg(null);
    setIsDragging(false);

    // Clear file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }

    // Scroll the Import card into view and focus the URL field
    setTimeout(() => {
      importCardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      rosterUrlRef.current?.focus();
    }, 50);
  };

  // ── Inline entry ──────────────────────────────────────────────────────────

  const handleAddRow = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!newName.trim() || !newJersey.trim()) return;
    setIsSaving(true);
    try {
      await photoTaggerClient.addRosterEntry(newJersey.trim(), newName.trim(), newTeam, teamYear, teamColor.trim() || undefined);
      setNewName('');
      setNewJersey('');
      await loadRoster();
      nameInputRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add player');
    } finally {
      setIsSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAddRow();
  };

  const handleDelete = async (id: number) => {
    try {
      await photoTaggerClient.deleteRosterEntry(id);
      setEntries(prev => prev.filter(r => r.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete entry');
    }
  };

  const handleDeleteRoster = async () => {
    if (!selectedTeam || !selectedYear) return;
    const confirmed = window.confirm(
      `Delete all ${selectedTeam} (${selectedYear}) players? This cannot be undone.`
    );
    if (!confirmed) return;

    try {
      setIsSaving(true);
      // Delete all entries for this team/year
      const entriesToDelete = entries.filter(
        e => e.team_name === selectedTeam && e.team_year === selectedYear
      );

      await Promise.all(
        entriesToDelete.map(e => photoTaggerClient.deleteRosterEntry(e.id))
      );

      await loadRoster();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete roster');
    } finally {
      setIsSaving(false);
    }
  };

  const updateContextTeam = (index: number, patch: Partial<GameContextTeam>) => {
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
      await loadRoster();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save game context');
    }
  };

  // ── Reset all data ────────────────────────────────────────────────────────

  const handleResetAllData = async () => {
    setShowResetConfirm(false);
    setIsResetting(true);
    try {
      await photoTaggerClient.resetAllData();
      // Full page reload clears ALL component state across every tab
      // (Gallery, Review, Players, sidebar — every page has its own cache)
      window.location.reload();
    } catch (err) {
      setIsResetting(false);
      setError(err instanceof Error ? err.message : 'Reset failed — check backend logs');
    }
  };

  // ── Individual Player Editing ──────────────────────────────────────────────

  const handleEditOpen = (entry: RosterEntry) => {
    setEditingEntry(entry);
    setEditForm({
      player_name: entry.player_name,
      jersey_number: entry.jersey_number,
      team_name: entry.team_name,
      team_year: entry.team_year,
      uniform_color: entry.uniform_color || '',
    });
    setEditError(null);
  };

  const handleEditChange = (field: string, value: any) => {
    setEditForm(prev => ({ ...prev, [field]: value }));
  };

  const handleEditSave = async () => {
    if (!editingEntry) return;
    if (!editForm.player_name.trim()) {
      setEditError('Player name cannot be empty');
      return;
    }
    if (!editForm.jersey_number.trim()) {
      setEditError('Jersey number cannot be empty');
      return;
    }

    setIsSavingEdit(true);
    setEditError(null);
    try {
      await photoTaggerClient.updateRosterEntry(editingEntry.id, {
        player_name: editForm.player_name.trim(),
        jersey_number: editForm.jersey_number.trim(),
        team_name: editForm.team_name,
        team_year: editForm.team_year,
        uniform_color: editForm.uniform_color.trim() || undefined,
      });
      await loadRoster();
      setEditingEntry(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to update entry';
      setEditError(msg);
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleEditCancel = () => {
    setEditingEntry(null);
    setEditForm({
      player_name: '',
      jersey_number: '',
      team_name: '',
      team_year: 2026,
      uniform_color: '',
    });
    setEditError(null);
  };

  // ── Bulk Roster Editing ────────────────────────────────────────────────────

  const handleOpenBulkEdit = () => {
    if (!selectedTeam || !selectedYear) return;
    setBulkEditForm({
      team_name: selectedTeam,
      team_year: selectedYear,
    });
    setBulkEditError(null);
    setShowBulkEditModal(true);
  };

  const handleBulkEditChange = (field: string, value: any) => {
    setBulkEditForm(prev => ({ ...prev, [field]: value }));
  };

  const handleBulkEditSave = async () => {
    if (!bulkEditForm.team_name.trim()) {
      setBulkEditError('Team name cannot be empty');
      return;
    }
    if (!selectedTeam || !selectedYear) return;

    setIsSavingBulk(true);
    setBulkEditError(null);
    try {
      // Get all entries that match the current filter
      const entriesToUpdate = entries.filter(
        e => e.team_name === selectedTeam && e.team_year === selectedYear
      );

      // Update each entry with the new team name/year
      await Promise.all(
        entriesToUpdate.map(entry =>
          photoTaggerClient.updateRosterEntry(entry.id, {
            team_name: bulkEditForm.team_name.trim(),
            team_year: bulkEditForm.team_year,
          })
        )
      );

      await loadRoster();
      setShowBulkEditModal(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to update roster';
      setBulkEditError(msg);
    } finally {
      setIsSavingBulk(false);
    }
  };

  const handleBulkEditCancel = () => {
    setShowBulkEditModal(false);
    setBulkEditForm({ team_name: '', team_year: 2026 });
    setBulkEditError(null);
  };

  // ── Bulk import ───────────────────────────────────────────────────────────

  /** Clear only the Import card fields — called automatically after a successful import. */
  const clearImportForm = () => {
    setRosterUrl('');
    setImportTeam('');
    setImportTeamYear(2026);
    setDuplicatePolicy('replace');
    setIsDragging(false);
    setShowImportTeamPills(true);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const formatImportMessage = (result: { imported: number; skipped: number; failed: number; errors?: string[] }) => {
    const parts = [`${result.imported} imported`];
    if (result.skipped > 0) parts.push(`${result.skipped} skipped`);
    if (result.failed > 0) parts.push(`${result.failed} failed`);
    const detail = result.errors?.length ? ` · ${result.errors.slice(0, 2).join('; ')}` : '';
    return `${parts.join(', ')}${detail}`;
  };

  const importFile = async (file: File) => {
    setImportMsg(null);
    setIsParsing(true);
    try {
      // Infer team name and year from filename
      let teamName = importTeam;
      let teamYear = importTeamYear;
      try {
        const inferResponse = await fetch('http://127.0.0.1:5001/api/roster/infer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: file.name }),
        });
        if (inferResponse.ok) {
          const inferred = await inferResponse.json();
          if (inferred.team_name) teamName = inferred.team_name;
          if (inferred.team_year) teamYear = inferred.team_year;
          setImportTeam(teamName);
          setImportTeamYear(teamYear);
        }
      } catch {
        // Inference failed, continue with current values
      }

      const result = await photoTaggerClient.importRosterFile(file, teamName, teamYear, duplicatePolicy);
      await loadRoster();
      setImportMsg({ type: result.failed === 0 ? 'success' : 'error', text: formatImportMessage(result) });
      if (result.failed === 0) clearImportForm();
    } catch (err) {
      setImportMsg({ type: 'error', text: err instanceof Error ? err.message : 'Import failed' });
    } finally {
      setIsParsing(false);
    }
  };

  const importUrl = async () => {
    if (!rosterUrl.trim()) return;
    setImportMsg(null);
    setIsParsing(true);
    try {
      // Infer team name and year from URL (USA Ultimate pages)
      let teamName = importTeam;
      let teamYear = importTeamYear;
      try {
        const inferResponse = await fetch('http://127.0.0.1:5001/api/roster/infer-url', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: rosterUrl.trim() }),
        });
        if (inferResponse.ok) {
          const inferred = await inferResponse.json();
          if (inferred.team_name) teamName = inferred.team_name;
          if (inferred.team_year) teamYear = inferred.team_year;
          setImportTeam(teamName);
          setImportTeamYear(teamYear);
        }
      } catch {
        // Inference failed, continue with current values
      }

      const result = await photoTaggerClient.importRosterUrl(rosterUrl.trim(), teamName, teamYear, duplicatePolicy);
      await loadRoster();
      setImportMsg({ type: result.failed === 0 ? 'success' : 'error', text: formatImportMessage(result) });
      if (result.failed === 0) clearImportForm();
    } catch (err) {
      setImportMsg({ type: 'error', text: err instanceof Error ? err.message : 'URL import failed' });
    } finally {
      setIsParsing(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!file.name.match(/\.(csv|txt|md|xlsx|pdf)$/i)) {
      setImportMsg({ type: 'error', text: 'Use a CSV, TXT, MD, XLSX, or PDF roster file.' });
      return;
    }
    importFile(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;
    if (!file.name.match(/\.(csv|txt|md|xlsx|pdf)$/i)) {
      setImportMsg({ type: 'error', text: 'Use a CSV, TXT, MD, XLSX, or PDF roster file.' });
      return;
    }
    importFile(file);
  };

  const filtered = entries.filter(e => {
    const teamMatch = !selectedTeam || e.team_name === selectedTeam;
    const yearMatch = !selectedYear || e.team_year === selectedYear;
    return teamMatch && yearMatch;
  });

  const teamGroups = rosterTeams.filter(t => entries.some(e => e.team_name === t));
  const yearGroups = Array.from(new Set(entries.map(e => e.team_year))).sort((a, b) => b - a);

  return (
    <SidebarLayout
      sidebar={
        <HierarchicalSidebar
          pageType="roster"
          rosterEntries={entries}
        />
      }
      children={
        <div className="w-full py-4 space-y-6">

      {/* ── Danger zone banner ──────────────────────────────────────────────── */}
      <div className="bg-[#FFF0F0] border-2 border-red-500 rounded-2xl px-5 py-3 flex items-center justify-between gap-4">
        <div>
          <p className="font-outfit font-bold text-red-600 text-sm">Danger zone</p>
          <p className="font-jakarta text-xs text-red-500 mt-0.5">
            Permanently delete all photos, faces, players, and rosters from the database.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowResetConfirm(true)}
          disabled={isResetting}
          className="flex-shrink-0 font-jakarta font-bold text-sm text-white bg-red-600 hover:bg-red-700 active:bg-red-800 px-5 py-2 rounded-full border-2 border-red-800 shadow-[3px_3px_0px_0px_rgba(153,27,27,0.5)] transition-colors disabled:opacity-50 whitespace-nowrap"
        >
          {isResetting ? 'Deleting…' : '🗑 Delete All Data'}
        </button>
      </div>

      {/* ── Confirmation modal ───────────────────────────────────────────────── */}
      {showResetConfirm && (
        <div className="fixed inset-0 z-50 bg-foreground/70 flex items-center justify-center p-4">
          <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg max-w-sm w-full p-6 space-y-4">
            <div className="flex items-start gap-3">
              <span className="text-2xl flex-shrink-0">⚠️</span>
              <div>
                <h2 className="font-outfit text-lg font-extrabold text-foreground">Delete all data?</h2>
                <p className="font-jakarta text-sm text-muted-fg mt-1">
                  This will permanently remove <strong>all photos, detected faces, face clusters, player assignments, and rosters</strong> from the database. This cannot be undone.
                </p>
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowResetConfirm(false)}
                className="flex-1 font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground bg-white hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleResetAllData}
                className="flex-1 font-jakarta font-bold text-sm text-white bg-red-600 hover:bg-red-700 px-4 py-2 rounded-full border-2 border-red-800 shadow-[3px_3px_0px_0px_rgba(153,27,27,0.5)] transition-colors"
              >
                Yes, delete everything
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-outfit text-4xl font-extrabold text-foreground">Roster</h1>
          <p className="mt-2 font-jakarta text-muted-fg">
            {entries.length} players across {teamGroups.length || '—'} teams
          </p>
        </div>
        <button
          type="button"
          onClick={clearAllForms}
          className="btn-candy bg-accent text-white font-jakarta font-bold px-5 py-2 rounded-full border-2 border-foreground shadow-pop whitespace-nowrap mt-1"
        >
          + Add Roster
        </button>
      </div>

      {error && (
        <div role="alert" aria-live="assertive" className="bg-white border-2 border-secondary rounded-xl shadow-pop-pink p-4 flex items-center justify-between">
          <p className="font-jakarta text-sm text-foreground">⚠️ {error}</p>
          <button onClick={() => setError(null)} className="font-jakarta text-xs text-muted-fg hover:text-foreground underline">Dismiss</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        {/* ── Bulk Import Zone ─────────────────────────────────────────────── */}
        <div ref={importCardRef} className="bg-white border-2 border-foreground rounded-2xl shadow-pop-yellow p-6 space-y-4 relative overflow-hidden">
          <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-tertiary rounded-full border-2 border-foreground opacity-80" />
          <h2 className="font-outfit text-lg font-bold text-foreground">Import Roster</h2>

          {/* Drop zone (also click-to-browse) */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.txt,.md,.xlsx,.pdf,text/csv,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={handleFileSelect}
            className="hidden"
          />
          <div
            onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click(); }}
            role="button"
            tabIndex={0}
            aria-label="Drag and drop a roster file, or click to browse"
            className={`relative cursor-pointer border-2 border-dashed rounded-xl p-8 text-center transition-colors focus:outline-none focus:ring-2 focus:ring-accent ${
              isDragging ? 'border-accent bg-accent/5' : 'border-frame bg-muted/30 hover:border-foreground'
            }`}
          >
            {/* Parsing overlay */}
            {isParsing && (
              <div className="absolute inset-0 z-10 bg-white/85 rounded-xl flex flex-col items-center justify-center gap-2">
                <span className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin block" />
                <p className="font-jakarta text-sm font-bold text-foreground">Importing roster…</p>
              </div>
            )}
            <svg width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" className="mx-auto mb-3 text-muted-fg">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <p className="font-jakarta text-sm font-semibold text-foreground">
              {isDragging ? 'Drop to import…' : 'Drag & drop roster here'}
            </p>
            <p className="font-jakarta text-xs text-muted-fg mt-1">CSV, TXT, MD, XLSX, PDF — or click to browse</p>
          </div>

          <div className="space-y-2">
            <label htmlFor="rosterUrl" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground">
              Roster URL
            </label>
            <div className="flex gap-2">
              <input
                id="rosterUrl"
                ref={rosterUrlRef}
                type="url"
                value={rosterUrl}
                onChange={e => setRosterUrl(e.target.value)}
                className="geo-input flex-1 min-w-0 px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
              />
              <button
                type="button"
                onClick={importUrl}
                disabled={isParsing || !rosterUrl.trim()}
                className="btn-candy bg-accent text-white font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 whitespace-nowrap"
              >
                Import
              </button>
            </div>
          </div>

          {/* Team selector for import */}
          <div>
            <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Import as team
            </label>
            <div className="space-y-2">
              {showImportTeamPills && rosterTeams.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {rosterTeams.map(team => (
                    <button
                      key={team}
                      onClick={() => { setImportTeam(team); setShowImportTeamPills(true); }}
                      className={`font-jakarta text-sm px-3 py-1.5 rounded-full border-2 transition-colors ${
                        importTeam === team
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
                id="importTeam"
                type="text"
                value={importTeam}
                onChange={e => { setImportTeam(e.target.value); setShowImportTeamPills(true); }}
                className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
              />
            </div>
          </div>

          <div>
            <label htmlFor="importTeamYear" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
              Year
            </label>
            <input
              id="importTeamYear"
              type="number"
              value={importTeamYear}
              onChange={e => setImportTeamYear(Number(e.target.value) || 2026)}
              className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
            />
          </div>

          {importMsg && (
            <div role={importMsg.type === 'error' ? 'alert' : 'status'} aria-live="polite"
              className={`p-3 rounded-xl border-2 font-jakarta text-sm ${importMsg.type === 'success' ? 'bg-quaternary/10 border-quaternary' : 'bg-secondary/10 border-secondary'}`}>
              {importMsg.text}
            </div>
          )}
        </div>

        {/* ── Add Player ───────────────────────────────────────────────────── */}
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop p-6 space-y-4 relative overflow-hidden">
          <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-accent rounded-full border-2 border-foreground opacity-70" />
          <h2 className="font-outfit text-lg font-bold text-foreground">Add Player</h2>

          <form onSubmit={handleAddRow} className="space-y-3">
            <div>
              <label htmlFor="newName" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">Name</label>
              <input
                id="newName"
                ref={nameInputRef}
                type="text"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={handleKeyDown}
                className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
              />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label htmlFor="newJersey" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">#</label>
                <input
                  id="newJersey"
                  type="text"
                  value={newJersey}
                  onChange={e => setNewJersey(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground text-center"
                />
              </div>
              <div>
                <label htmlFor="newTeam" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">Team</label>
                <input
                  id="newTeam"
                  type="text"
                  value={newTeam}
                  onChange={e => setNewTeam(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                />
              </div>
              <div>
                <label htmlFor="newYear" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">Year</label>
                <input
                  id="newYear"
                  type="number"
                  value={teamYear}
                  onChange={e => setTeamYear(Number(e.target.value) || 2026)}
                  onKeyDown={handleKeyDown}
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={isSaving || !newName.trim() || !newJersey.trim()}
              className="btn-candy w-full bg-accent text-white font-jakarta font-bold px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40"
            >
              + Add Player
            </button>
          </form>
        </div>
      </div>

      {/* ── Roster Table ─────────────────────────────────────────────────────── */}
      <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg overflow-hidden">
        {/* Table toolbar */}
        <div className="px-5 py-4 border-b-2 border-frame flex items-center justify-between gap-4">
          <div>
            <h2 className="font-outfit text-lg font-bold text-foreground">
              All Players ({filtered.length})
            </h2>
            {selectedTeam && selectedYear && (
              <p className="font-jakarta text-sm text-muted-fg mt-1">
                Filtered to {selectedTeam} ({selectedYear})
              </p>
            )}
          </div>
          {selectedTeam && selectedYear && (
            <div className="flex gap-2">
              <button
                onClick={handleOpenBulkEdit}
                disabled={isSaving || filtered.length === 0}
                className="btn-candy bg-accent text-white font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 whitespace-nowrap"
              >
                Edit Roster
              </button>
              <button
                onClick={handleDeleteRoster}
                disabled={isSaving || filtered.length === 0}
                className="btn-candy bg-secondary text-white font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 whitespace-nowrap"
              >
                Delete Roster
              </button>
            </div>
          )}
        </div>

        {isLoading ? (
          <div className="flex justify-center py-12"><LoadingSpinner message="Loading roster…" /></div>
        ) : filtered.length === 0 ? (
          <div className="py-14 text-center">
            <p className="font-outfit text-lg font-bold text-foreground">No players yet</p>
            <p className="font-jakarta text-sm text-muted-fg mt-1">Add players above or import a roster</p>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b-2 border-frame bg-muted/40">
                <th className="text-left font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg px-5 py-3 w-16">#</th>
                <th className="text-left font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg px-3 py-3 w-16">Face</th>
                <th className="text-left font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg px-3 py-3">Name</th>
                <th className="text-left font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg px-3 py-3 hidden sm:table-cell">Team</th>
                <th className="text-left font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg px-3 py-3 hidden md:table-cell">Color</th>
                <th className="w-12 px-3 py-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry, i) => (
                <tr
                  key={entry.id}
                  className={`border-b border-frame/60 last:border-0 hover:bg-muted/20 transition-colors ${i % 2 === 0 ? '' : 'bg-muted/10'}`}
                >
                  <td className="px-5 py-3">
                    <span className="inline-flex items-center justify-center w-9 h-9 bg-accent rounded-lg border-2 border-foreground shadow-pop-sm">
                      <span className="font-outfit font-extrabold text-white text-sm">#{entry.jersey_number}</span>
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <div className="w-10 h-10 rounded-full overflow-hidden border-2 border-frame bg-muted flex items-center justify-center">
                      {entry.thumbnail_face_id ? (
                        <img
                          src={photoTaggerClient.getFaceCropUrl(entry.thumbnail_face_id)}
                          alt={`${entry.player_name} face`}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="text-muted-fg">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-3 font-jakarta font-semibold text-foreground text-sm">{entry.player_name}</td>
                  <td className="px-3 py-3 hidden sm:table-cell">
                    <span className="font-jakarta text-xs text-muted-fg bg-muted px-2 py-0.5 rounded-full">{entry.team_name}</span>
                  </td>
                  <td className="px-3 py-3 hidden md:table-cell">
                    <span className="font-jakarta text-xs text-muted-fg bg-muted px-2 py-0.5 rounded-full">{entry.uniform_color || '—'}</span>
                  </td>
                  <td className="px-3 py-3 text-right flex gap-2 justify-end">
                    <button
                      onClick={() => handleEditOpen(entry)}
                      className="font-jakarta text-xs text-muted-fg hover:text-accent border border-frame rounded-full px-2 py-0.5 hover:border-accent transition-colors"
                      aria-label={`Edit ${entry.player_name}`}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(entry.id)}
                      className="font-jakarta text-xs text-muted-fg hover:text-secondary border border-frame rounded-full px-2 py-0.5 hover:border-secondary transition-colors"
                      aria-label={`Remove ${entry.player_name}`}
                    >
                      Del
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Individual Player Edit Modal ─────────────────────────────────────── */}
      {editingEntry && (
        <div className="fixed inset-0 z-50 bg-foreground/70 flex items-center justify-center p-4">
          <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg max-w-md w-full p-6 space-y-4">
            <h2 className="font-outfit text-lg font-extrabold text-foreground">
              Edit {editingEntry.player_name}
            </h2>

            <div className="space-y-3">
              <div>
                <label htmlFor="editPlayerName" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
                  Player Name
                </label>
                <input
                  id="editPlayerName"
                  type="text"
                  value={editForm.player_name}
                  onChange={e => handleEditChange('player_name', e.target.value)}
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label htmlFor="editJersey" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
                    Jersey #
                  </label>
                  <input
                    id="editJersey"
                    type="text"
                    value={editForm.jersey_number}
                    onChange={e => handleEditChange('jersey_number', e.target.value)}
                    className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground text-center"
                  />
                </div>
                <div>
                  <label htmlFor="editYear" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
                    Year
                  </label>
                  <input
                    id="editYear"
                    type="number"
                    value={editForm.team_year}
                    onChange={e => handleEditChange('team_year', Number(e.target.value))}
                    className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="editTeam" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
                  Team Name
                </label>
                <input
                  id="editTeam"
                  type="text"
                  value={editForm.team_name}
                  onChange={e => handleEditChange('team_name', e.target.value)}
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                />
              </div>

              <div>
                <label htmlFor="editColor" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
                  Uniform Color
                </label>
                <input
                  id="editColor"
                  type="text"
                  value={editForm.uniform_color}
                  onChange={e => handleEditChange('uniform_color', e.target.value)}
                  placeholder="red, white, blue…"
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
                />
              </div>
            </div>

            {editError && (
              <div role="alert" className="bg-secondary/10 border-2 border-secondary rounded-xl p-3">
                <p className="font-jakarta text-xs text-secondary font-bold">{editError}</p>
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={handleEditCancel}
                disabled={isSavingEdit}
                className="flex-1 font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground bg-white hover:bg-muted disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleEditSave}
                disabled={isSavingEdit}
                className="flex-1 font-jakarta font-bold text-sm text-white bg-accent hover:bg-accent/80 px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-50 transition-colors"
              >
                {isSavingEdit ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Bulk Roster Edit Modal ──────────────────────────────────────────── */}
      {showBulkEditModal && selectedTeam && selectedYear && (
        <div className="fixed inset-0 z-50 bg-foreground/70 flex items-center justify-center p-4">
          <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg max-w-md w-full p-6 space-y-4">
            <h2 className="font-outfit text-lg font-extrabold text-foreground">
              Edit Roster: {selectedTeam} ({selectedYear})
            </h2>
            <p className="font-jakarta text-sm text-muted-fg">
              Update team name and/or year for all {filtered.length} player{filtered.length === 1 ? '' : 's'}
            </p>

            <div className="space-y-3">
              <div>
                <label htmlFor="bulkTeamName" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
                  New Team Name
                </label>
                <input
                  id="bulkTeamName"
                  type="text"
                  value={bulkEditForm.team_name}
                  onChange={e => handleBulkEditChange('team_name', e.target.value)}
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                />
              </div>

              <div>
                <label htmlFor="bulkYear" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
                  New Year
                </label>
                <input
                  id="bulkYear"
                  type="number"
                  value={bulkEditForm.team_year}
                  onChange={e => handleBulkEditChange('team_year', Number(e.target.value))}
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                />
              </div>
            </div>

            {bulkEditError && (
              <div role="alert" className="bg-secondary/10 border-2 border-secondary rounded-xl p-3">
                <p className="font-jakarta text-xs text-secondary font-bold">{bulkEditError}</p>
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={handleBulkEditCancel}
                disabled={isSavingBulk}
                className="flex-1 font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground bg-white hover:bg-muted disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleBulkEditSave}
                disabled={isSavingBulk}
                className="flex-1 font-jakarta font-bold text-sm text-white bg-accent hover:bg-accent/80 px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-50 transition-colors"
              >
                {isSavingBulk ? 'Updating…' : 'Update All'}
              </button>
            </div>
          </div>
        </div>
      )}
        </div>
      }
    />
  );
};

export default RosterPage;
