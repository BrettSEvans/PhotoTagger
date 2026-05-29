import React, { useState, useEffect, useRef } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from '../components/LoadingSpinner';
import type { RosterEntry } from '../types/index';

const TEAMS = ['All Teams', 'Carleton CUT', 'Pittsburgh En Sabah Nur', 'Manual Entry'];

export const RosterPage: React.FC = () => {
  const [entries, setEntries]       = useState<RosterEntry[]>([]);
  const [isLoading, setIsLoading]   = useState(true);
  const [filterTeam, setFilterTeam] = useState('All Teams');
  const [error, setError]           = useState<string | null>(null);

  // Inline entry form
  const [newName,   setNewName]   = useState('');
  const [newJersey, setNewJersey] = useState('');
  const [newTeam,   setNewTeam]   = useState('Manual Entry');
  const [isSaving,  setIsSaving]  = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);

  // CSV drag state
  const [isDragging, setIsDragging] = useState(false);
  const [isParsing,  setIsParsing]  = useState(false);
  const [csvMsg,     setCsvMsg]     = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { loadRoster(); }, []);

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

  // ── Inline entry ──────────────────────────────────────────────────────────

  const handleAddRow = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!newName.trim() || !newJersey.trim()) return;
    setIsSaving(true);
    try {
      await photoTaggerClient.addRosterEntry(newJersey.trim(), newName.trim(), newTeam);
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

  // ── CSV drag-and-drop ─────────────────────────────────────────────────────

  const parseCsv = async (file: File) => {
    setCsvMsg(null);
    setIsParsing(true);
    try {
      const text = await file.text();
      const lines = text.split('\n').filter(l => l.trim());
      if (lines.length < 2) { setCsvMsg({ type: 'error', text: 'File appears empty or has no data rows.' }); return; }

      const header = lines[0].toLowerCase();
      const hasName   = header.includes('name');
      const hasJersey = header.includes('jersey') || header.includes('number') || header.includes('#');
      if (!hasName || !hasJersey) {
        setCsvMsg({ type: 'error', text: 'Could not find "name" and "jersey"/"number" columns. Check your CSV headers.' });
        return;
      }

      const cols = lines[0].split(',').map(c => c.trim().toLowerCase());
      const nameIdx   = cols.findIndex(c => c.includes('name'));
      const jerseyIdx = cols.findIndex(c => c.includes('jersey') || c.includes('number') || c === '#');

      let added = 0, failed = 0;
      for (let i = 1; i < lines.length; i++) {
        const cells = lines[i].split(',').map(c => c.trim().replace(/^"|"$/g, ''));
        const name   = cells[nameIdx]   ?? '';
        const jersey = cells[jerseyIdx] ?? '';
        if (!name || !jersey) { failed++; continue; }
        try {
          await photoTaggerClient.addRosterEntry(jersey, name, newTeam);
          added++;
        } catch { failed++; }
      }

      await loadRoster();
      setCsvMsg({
        type: failed === 0 ? 'success' : 'error',
        text: failed === 0
          ? `✅ ${added} players imported successfully`
          : `⚠️ ${added} imported, ${failed} rows failed — check name/jersey columns`,
      });
    } finally {
      setIsParsing(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!file.name.match(/\.(csv|xlsx)$/i)) {
      setCsvMsg({ type: 'error', text: 'Only CSV files are supported (XLSX coming soon).' });
      return;
    }
    parseCsv(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;
    if (!file.name.match(/\.(csv|xlsx)$/i)) {
      setCsvMsg({ type: 'error', text: 'Only CSV files are supported (XLSX coming soon).' });
      return;
    }
    parseCsv(file);
  };

  const filtered = filterTeam === 'All Teams'
    ? entries
    : entries.filter(e => e.team_name === filterTeam);

  const teamGroups = TEAMS.slice(1).filter(t => entries.some(e => e.team_name === t));

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
        {/* ── Left: Bulk Import Zone ───────────────────────────────────────── */}
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-yellow p-6 space-y-4 relative overflow-hidden">
          <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-tertiary rounded-full border-2 border-foreground opacity-80" />
          <h2 className="font-outfit text-lg font-bold text-foreground">Bulk Import</h2>
          <p className="font-jakarta text-xs text-muted-fg">Drop a CSV with "name" and "jersey" columns</p>

          {/* Drop zone (also click-to-browse) */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
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
            aria-label="Drag and drop a CSV roster, or click to browse"
            className={`relative cursor-pointer border-2 border-dashed rounded-xl p-8 text-center transition-colors focus:outline-none focus:ring-2 focus:ring-accent ${
              isDragging ? 'border-accent bg-accent/5' : 'border-frame bg-muted/30 hover:border-foreground'
            }`}
          >
            {/* Parsing overlay */}
            {isParsing && (
              <div className="absolute inset-0 z-10 bg-white/85 rounded-xl flex flex-col items-center justify-center gap-2">
                <span className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin block" />
                <p className="font-jakarta text-sm font-bold text-foreground">Parsing columns…</p>
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
            <p className="font-jakarta text-xs text-muted-fg mt-1">CSV only — or click to browse</p>
          </div>

          {/* Team selector for import */}
          <div>
            <label className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-1">
              Import as team
            </label>
            <select
              value={newTeam}
              onChange={e => setNewTeam(e.target.value)}
              className="geo-input w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground appearance-none cursor-pointer"
            >
              <option>Manual Entry</option>
              <option>Carleton CUT</option>
              <option>Pittsburgh En Sabah Nur</option>
            </select>
          </div>

          {csvMsg && (
            <div role={csvMsg.type === 'error' ? 'alert' : 'status'} aria-live="polite"
              className={`p-3 rounded-xl border-2 font-jakarta text-sm ${csvMsg.type === 'success' ? 'bg-quaternary/10 border-quaternary' : 'bg-secondary/10 border-secondary'}`}>
              {csvMsg.text}
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
            <p className="font-jakarta text-sm text-muted-fg mt-1">Add players above or import a CSV</p>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b-2 border-frame bg-muted/40">
                <th className="text-left font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg px-5 py-3 w-16">#</th>
                <th className="text-left font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg px-3 py-3">Name</th>
                <th className="text-left font-jakarta text-xs font-bold uppercase tracking-wider text-muted-fg px-3 py-3 hidden sm:table-cell">Team</th>
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
                  <td className="px-3 py-3 font-jakarta font-semibold text-foreground text-sm">{entry.player_name}</td>
                  <td className="px-3 py-3 hidden sm:table-cell">
                    <span className="font-jakarta text-xs text-muted-fg bg-muted px-2 py-0.5 rounded-full">{entry.team_name}</span>
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
