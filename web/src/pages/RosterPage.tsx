import React, { useState, useEffect, useRef, useMemo } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from '../components/LoadingSpinner';
import type { GameContextTeam, RosterEntry } from '../types/index';

export const RosterPage: React.FC = () => {
  const [entries, setEntries]       = useState<RosterEntry[]>([]);
  const [isLoading, setIsLoading]   = useState(true);
  const [filterTeam, setFilterTeam] = useState('All Teams');
  const [error, setError]           = useState<string | null>(null);

  // Inline entry form
  const [newName,   setNewName]   = useState('');
  const [newJersey, setNewJersey] = useState('');
  const [newTeam,   setNewTeam]   = useState('');
  const [teamYear,  setTeamYear]  = useState(2026);
  const [teamColor, setTeamColor] = useState('');
  const [isSaving,  setIsSaving]  = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);

  const [gameContext, setGameContext] = useState<GameContextTeam[]>([]);
  const [contextMsg, setContextMsg] = useState<string | null>(null);

  // Bulk import state
  const [isDragging, setIsDragging] = useState(false);
  const [isParsing,  setIsParsing]  = useState(false);
  const [importMsg,  setImportMsg]  = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [rosterUrl,  setRosterUrl]  = useState('');
  const [importTeam, setImportTeam] = useState('');
  const [importTeamYear,   setImportTeamYear]   = useState(2026);
  const [duplicatePolicy, setDuplicatePolicy] = useState<'replace' | 'skip'>('replace');
  const [importTeamColor, setImportTeamColor] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  // ── Bulk import ───────────────────────────────────────────────────────────

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
      const result = await photoTaggerClient.importRosterFile(file, importTeam, importTeamYear, duplicatePolicy, importTeamColor.trim() || undefined);
      await loadRoster();
      setImportMsg({ type: result.failed === 0 ? 'success' : 'error', text: formatImportMessage(result) });
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
      const result = await photoTaggerClient.importRosterUrl(rosterUrl.trim(), importTeam, importTeamYear, duplicatePolicy, importTeamColor.trim() || undefined);
      await loadRoster();
      setImportMsg({ type: result.failed === 0 ? 'success' : 'error', text: formatImportMessage(result) });
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

  const filtered = filterTeam === 'All Teams'
    ? entries
    : entries.filter(e => e.team_name === filterTeam);

  const teamGroups = rosterTeams.filter(t => entries.some(e => e.team_name === t));

  return (
    <div className="w-full max-w-6xl mx-auto py-4 space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-outfit text-4xl font-extrabold text-foreground">Roster</h1>
        <p className="mt-2 font-jakarta text-muted-fg">
          {entries.length} players across {teamGroups.length || '—'} teams
        </p>
      </div>

      {error && (
        <div role="alert" aria-live="assertive" className="bg-white border-2 border-secondary rounded-xl shadow-pop-pink p-4 flex items-center justify-between">
          <p className="font-jakarta text-sm text-foreground">⚠️ {error}</p>
          <button onClick={() => setError(null)} className="font-jakarta text-xs text-muted-fg hover:text-foreground underline">Dismiss</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="md:col-span-2 bg-white border-2 border-foreground rounded-2xl shadow-pop-mint p-5 space-y-4">
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[0, 1].map(index => (
              <div key={index} className="grid grid-cols-[1fr_88px_110px] gap-2">
                <select
                  value={gameContext[index]?.team_name ?? ''}
                  onChange={e => updateContextTeam(index, { team_name: e.target.value })}
                  className="geo-input min-w-0 px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
                >
                  <option value="">Select team</option>
                  {rosterTeams.map(team => <option key={team}>{team}</option>)}
                </select>
                <input
                  type="number"
                  value={gameContext[index]?.team_year || ''}
                  placeholder="2026"
                  onChange={e => updateContextTeam(index, { team_year: Number(e.target.value) || 0 })}
                  className="geo-input px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
                />
                <input
                  type="text"
                  value={gameContext[index]?.uniform_color ?? ''}
                  onChange={e => updateContextTeam(index, { uniform_color: e.target.value })}
                  placeholder={index === 0 ? 'red' : 'white'}
                  className="geo-input px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
                />
              </div>
            ))}
          </div>
          {contextMsg && <p className="font-jakarta text-xs font-semibold text-foreground">{contextMsg}</p>}
        </div>

        {/* ── Left: Bulk Import Zone ───────────────────────────────────────── */}
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-yellow p-6 space-y-4 relative overflow-hidden">
          <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-tertiary rounded-full border-2 border-foreground opacity-80" />
          <h2 className="font-outfit text-lg font-bold text-foreground">Bulk Import</h2>
          <p className="font-jakarta text-xs text-muted-fg">Drop a roster file or paste a roster URL</p>

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
                type="url"
                value={rosterUrl}
                onChange={e => setRosterUrl(e.target.value)}
                placeholder="https://play.usaultimate.org/events/teams/?EventTeamId=…"
                className="geo-input flex-1 min-w-0 px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
              />
              <button
                type="button"
                onClick={importUrl}
                disabled={isParsing || !rosterUrl.trim()}
                className="btn-candy bg-accent text-white font-jakarta font-bold text-sm px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 whitespace-nowrap"
              >
                Scrape
              </button>
            </div>
          </div>

          {/* Team selector for import */}
          <div>
            <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Import as team
            </label>
            <div className="space-y-2">
              {rosterTeams.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {rosterTeams.map(team => (
                    <button
                      key={team}
                      onClick={() => setImportTeam(team)}
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
              <div>
                <label htmlFor="importTeam" className="block font-jakarta text-xs text-muted-fg mb-1">
                  Or type a new team name:
                </label>
                <input
                  id="importTeam"
                  type="text"
                  value={importTeam}
                  onChange={e => setImportTeam(e.target.value)}
                  placeholder="Team name…"
                  className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-[1fr_110px_130px] gap-3">
            <div>
              <label htmlFor="importTeamColor" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
                Team uniform color
              </label>
              <input
                id="importTeamColor"
                type="text"
                value={importTeamColor}
                onChange={e => setImportTeamColor(e.target.value)}
                placeholder="red, white, blue…"
                className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
              />
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
          </div>

          <div>
            <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
              Existing jerseys
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: 'replace', label: 'Replace existing' },
                { value: 'skip', label: 'Skip existing' },
              ].map(option => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setDuplicatePolicy(option.value as 'replace' | 'skip')}
                  className={`font-jakarta text-xs font-bold px-3 py-2 rounded-xl border-2 transition-colors ${
                    duplicatePolicy === option.value
                      ? 'bg-accent text-white border-foreground shadow-pop-sm'
                      : 'bg-white text-foreground border-frame hover:bg-muted'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {importMsg && (
            <div role={importMsg.type === 'error' ? 'alert' : 'status'} aria-live="polite"
              className={`p-3 rounded-xl border-2 font-jakarta text-sm ${importMsg.type === 'success' ? 'bg-quaternary/10 border-quaternary' : 'bg-secondary/10 border-secondary'}`}>
              {importMsg.text}
            </div>
          )}
        </div>

        {/* ── Right: Inline Creation Matrix ───────────────────────────────── */}
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop p-6 space-y-4 relative overflow-hidden">
          <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-accent rounded-full border-2 border-foreground opacity-70" />
          <h2 className="font-outfit text-lg font-bold text-foreground">Add Player</h2>

          <form onSubmit={handleAddRow} className="flex gap-2 items-end">
            <div className="flex-1">
              <label htmlFor="newName" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">Name</label>
              <input
                id="newName"
                ref={nameInputRef}
                type="text"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Player name…"
                className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg"
              />
            </div>
            <div className="w-20">
              <label htmlFor="newJersey" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">#</label>
              <input
                id="newJersey"
                type="text"
                value={newJersey}
                onChange={e => setNewJersey(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="23"
                className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg text-center"
              />
            </div>
            <button
              type="submit"
              disabled={isSaving || !newName.trim() || !newJersey.trim()}
              className="btn-candy bg-accent text-white font-jakarta font-bold px-4 py-2 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 whitespace-nowrap"
            >
              + Add
            </button>
          </form>
          <p className="font-jakarta text-xs text-muted-fg">Press Enter to add and stay in name field</p>
        </div>
      </div>

      {/* ── Roster Table ─────────────────────────────────────────────────────── */}
      <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg overflow-hidden">
        {/* Table toolbar */}
        <div className="flex items-center justify-between px-5 py-4 border-b-2 border-frame">
          <h2 className="font-outfit text-lg font-bold text-foreground">
            {filterTeam === 'All Teams' ? `All Players (${entries.length})` : `${filterTeam} (${filtered.length})`}
          </h2>
          <div className="flex gap-2">
            {['All Teams', ...teamGroups].map(t => (
              <button
                key={t}
                onClick={() => setFilterTeam(t)}
                className={`font-jakarta text-xs font-bold px-3 py-1.5 rounded-full border-2 transition-colors ${
                  filterTeam === t
                    ? 'bg-accent text-white border-foreground shadow-pop-sm'
                    : 'bg-white text-foreground border-frame hover:bg-tertiary hover:border-foreground'
                }`}
              >
                {t === 'All Teams' ? t : t.split(' ')[0]}
              </button>
            ))}
          </div>
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
                  <td className="px-3 py-3 text-right">
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
    </div>
  );
};

export default RosterPage;
