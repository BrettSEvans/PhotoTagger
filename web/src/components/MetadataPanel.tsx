import React, { useState } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import { AssignPlayerPanel } from './AssignPlayerPanel';
import type { PhotoMetadata } from '../types/index';

interface MetadataPanelProps {
  metadata: PhotoMetadata | null;
  isLoading: boolean;
  showNames: boolean;
  showBoxes: boolean;
  onToggleNames: () => void;
  onToggleBoxes: () => void;
  /** Called after a person is successfully assigned, to refresh the panel + overlay. */
  onAssigned: () => void;
  hoveredPersonId: number | null;
  onHoverPerson: (id: number | null) => void;
}

function formatBytes(bytes: number | null | undefined): string | null {
  if (!bytes) return null;
  return `${Math.round(bytes / 1024)} KB`;
}

function formatDate(iso: string | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso.includes('T') || iso.includes(' ') ? iso.replace(' ', 'T') : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const Toggle: React.FC<{ label: string; on: boolean; onClick: () => void }> = ({ label, on, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg border-2 border-foreground px-2 py-1.5 font-jakarta text-xs font-bold transition-colors ${
      on ? 'bg-accent text-accent-fg' : 'bg-white text-foreground'
    }`}
  >
    <span className={`h-1.5 w-1.5 rounded-full ${on ? 'bg-white' : 'bg-muted-fg/50'}`} />
    {label}
  </button>
);

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="border-b border-frame px-4 py-3">
    <h4 className="font-jakarta text-[10px] font-bold uppercase tracking-wide text-muted-fg mb-2">{title}</h4>
    {children}
  </div>
);

const Row: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex justify-between gap-3 py-0.5 font-jakarta text-xs">
    <span className="text-muted-fg">{label}</span>
    <span className="text-foreground text-right break-words">{value}</span>
  </div>
);

export const MetadataPanel: React.FC<MetadataPanelProps> = ({
  metadata,
  isLoading,
  showNames,
  showBoxes,
  onToggleNames,
  onToggleBoxes,
  onAssigned,
  hoveredPersonId,
  onHoverPerson,
}) => {
  const [assigningClusterId, setAssigningClusterId] = useState<number | null>(null);
  const [showGameForm, setShowGameForm] = useState(false);
  const [gameForm, setGameForm] = useState({ team_name: '', team_year: '', tournament: '' });
  const [savingGame, setSavingGame] = useState(false);

  const handleSaveGame = async () => {
    if (!metadata?.library.batch_id) return;
    setSavingGame(true);
    try {
      await photoTaggerClient.updateBatch(metadata.library.batch_id, {
        team_name: gameForm.team_name || undefined,
        team_year: gameForm.team_year ? parseInt(gameForm.team_year, 10) : undefined,
        tournament: gameForm.tournament || undefined,
      } as any);
      setShowGameForm(false);
      onAssigned(); // reuse: triggers a metadata refetch in the parent
    } finally {
      setSavingGame(false);
    }
  };

  return (
    <div className="w-full md:w-[300px] bg-cream border-t-2 md:border-t-0 md:border-l-2 border-foreground flex flex-col max-h-[40vh] md:max-h-none overflow-y-auto">
      <div className="flex gap-2 px-4 py-3 bg-muted/40 border-b-2 border-foreground flex-shrink-0">
        <Toggle label="Names" on={showNames} onClick={onToggleNames} />
        <Toggle label="Boxes" on={showBoxes} onClick={onToggleBoxes} />
      </div>

      {isLoading && (
        <div className="px-4 py-6 font-jakarta text-xs text-muted-fg">Loading metadata…</div>
      )}

      {!isLoading && metadata && (
        <>
          <Section title="File">
            <p className="font-jakarta text-xs text-foreground break-all leading-relaxed">{metadata.file.filename}</p>
          </Section>

          {metadata.image && (
            <Section title="Image">
              <Row label="Dimensions" value={`${metadata.image.width} × ${metadata.image.height}`} />
              {formatBytes(metadata.image.size_bytes) && <Row label="Size" value={formatBytes(metadata.image.size_bytes)} />}
              <Row label="Format" value={`${metadata.image.format} · ${metadata.image.mode}`} />
            </Section>
          )}

          {metadata.jersey_ocr && (
            <Section title="Jersey / OCR">
              <Row label="Detected" value={metadata.jersey_ocr.detected_numbers.map((n) => `#${n}`).join(', ')} />
              {metadata.jersey_ocr.confidence !== undefined && (
                <Row label="Confidence" value={`${Math.round(metadata.jersey_ocr.confidence * 100)}%`} />
              )}
            </Section>
          )}

          <Section title="Library">
            {formatDate(metadata.library.ingested) && <Row label="Ingested" value={formatDate(metadata.library.ingested)} />}
            {metadata.library.batch && <Row label="Batch" value={metadata.library.batch} />}
          </Section>

          <Section title="Game">
            {metadata.game ? (
              <>
                {metadata.game.team_a && <Row label="Team A" value={metadata.game.team_a} />}
                {metadata.game.team_b && <Row label="Team B" value={metadata.game.team_b} />}
                {metadata.game.year && <Row label="Year" value={metadata.game.year} />}
                {metadata.game.tournament && <Row label="Tournament" value={metadata.game.tournament} />}
              </>
            ) : showGameForm ? (
              <div className="flex flex-col gap-2">
                <input
                  className="border-2 border-frame rounded px-2 py-1 text-xs font-jakarta"
                  placeholder="Team name"
                  value={gameForm.team_name}
                  onChange={(e) => setGameForm((f) => ({ ...f, team_name: e.target.value }))}
                />
                <input
                  className="border-2 border-frame rounded px-2 py-1 text-xs font-jakarta"
                  placeholder="Year"
                  value={gameForm.team_year}
                  onChange={(e) => setGameForm((f) => ({ ...f, team_year: e.target.value }))}
                />
                <input
                  className="border-2 border-frame rounded px-2 py-1 text-xs font-jakarta"
                  placeholder="Tournament"
                  value={gameForm.tournament}
                  onChange={(e) => setGameForm((f) => ({ ...f, tournament: e.target.value }))}
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleSaveGame}
                    disabled={savingGame}
                    className="btn-candy bg-accent text-accent-fg font-jakarta text-xs font-bold px-3 py-1.5 rounded-lg border-2 border-foreground disabled:opacity-50"
                  >
                    {savingGame ? 'Saving…' : 'Save'}
                  </button>
                  <button
                    onClick={() => setShowGameForm(false)}
                    className="font-jakarta text-xs font-bold px-3 py-1.5 text-muted-fg"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="bg-accent/10 border border-dashed border-accent rounded-lg p-3">
                <p className="font-jakarta text-[11px] text-foreground leading-relaxed mb-2">
                  No team or tournament recorded. Set this batch's team and tournament so it's captured for every
                  photo in the batch — and written into the photo's metadata.
                </p>
                <button
                  onClick={() => setShowGameForm(true)}
                  disabled={!metadata.library.batch_id}
                  className="btn-candy bg-accent text-accent-fg font-jakarta text-xs font-bold px-3 py-1.5 rounded-lg border-2 border-foreground disabled:opacity-50"
                >
                  + Add teams &amp; tournament
                </button>
              </div>
            )}
          </Section>

          <div className="px-4 py-3">
            <h4 className="font-jakarta text-[10px] font-bold uppercase tracking-wide text-muted-fg mb-2">
              People — {metadata.people.filter((p) => p.assigned).length} of {metadata.people.length} identified
            </h4>
            {metadata.people.length === 0 && (
              <p className="font-jakarta text-xs text-muted-fg">No faces detected in this photo.</p>
            )}
            <div className="flex flex-col gap-1.5">
              {metadata.people.map((person) => (
                <div key={person.id}>
                  <div
                    className="flex items-center gap-2 py-0.5"
                    onMouseEnter={() => onHoverPerson(person.id)}
                    onMouseLeave={() => onHoverPerson(null)}
                  >
                    <span
                      className={`flex-shrink-0 h-[19px] w-[19px] rounded-full flex items-center justify-center text-[10.5px] font-bold text-white bg-[#9333EA] ${
                        hoveredPersonId === person.id ? 'ring-2 ring-offset-1 ring-accent' : ''
                      }`}
                    >
                      {person.id}
                    </span>
                    {person.assigned ? (
                      <span className="font-jakarta text-xs text-foreground">{person.name}</span>
                    ) : (
                      <span className="font-jakarta text-xs text-muted-fg italic">Unassigned</span>
                    )}
                    {!person.assigned && person.cluster_id !== null && (
                      <button
                        onClick={() => setAssigningClusterId(assigningClusterId === person.cluster_id ? null : person.cluster_id)}
                        className="ml-auto font-jakarta text-[11px] text-accent underline"
                      >
                        Assign
                      </button>
                    )}
                  </div>
                  {assigningClusterId === person.cluster_id && person.cluster_id !== null && (
                    <div className="ml-6 mt-1 mb-2">
                      <AssignPlayerPanel
                        clusterId={person.cluster_id}
                        autoFocus
                        onAssigned={() => {
                          setAssigningClusterId(null);
                          onAssigned();
                        }}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default MetadataPanel;
