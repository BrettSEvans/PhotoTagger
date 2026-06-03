import React, { useState } from 'react';
import { RosterEntry, PhotoBatch } from '../types';
import { useSidebar } from '../contexts/SidebarContext';

type PageType = 'roster' | 'upload' | 'review' | 'players' | 'search' | 'gallery';

interface HierarchicalSidebarProps {
  pageType: PageType;
  rosterEntries?: RosterEntry[];
  batches?: PhotoBatch[];
  onAddGame?: () => void;
}

interface RosterHierarchy {
  year: number;
  teams: Array<{ team: string; count: number }>;
}

interface GameHierarchy {
  year: number;
  tournaments: Array<{
    tournament: string;
    games: Array<{ id: string; teamA: string; teamB: string; photoCount: number }>;
  }>;
}

function buildRosterHierarchy(entries: RosterEntry[]): RosterHierarchy[] {
  const byYear: Record<number, RosterEntry[]> = {};
  entries.forEach(entry => {
    if (!byYear[entry.team_year]) byYear[entry.team_year] = [];
    byYear[entry.team_year].push(entry);
  });

  return Object.entries(byYear)
    .map(([year, yearEntries]) => ({
      year: parseInt(year),
      teams: Array.from(
        new Map(yearEntries.map(e => [e.team_name, e])).keys()
      ).map(team => ({
        team,
        count: yearEntries.filter(e => e.team_name === team).length,
      })),
    }))
    .sort((a, b) => b.year - a.year);
}

function buildGameHierarchy(batches: PhotoBatch[]): GameHierarchy[] {
  const byYear: Record<number, PhotoBatch[]> = {};
  batches.forEach(batch => {
    if (batch.team_year !== null && batch.team_year !== undefined) {
      if (!byYear[batch.team_year]) byYear[batch.team_year] = [];
      byYear[batch.team_year].push(batch);
    }
  });

  return Object.entries(byYear)
    .map(([year, yearBatches]) => {
      const byTournament: Record<string, PhotoBatch[]> = {};
      yearBatches.forEach(batch => {
        const tournament = batch.tournament || 'Unnamed Tournament';
        if (!byTournament[tournament]) byTournament[tournament] = [];
        byTournament[tournament].push(batch);
      });

      return {
        year: parseInt(year),
        tournaments: Object.entries(byTournament).map(([tournament, tourBatches]) => ({
          tournament,
          games: tourBatches.map(batch => {
            const teamB = batch.name?.includes('vs')
              ? batch.name.split('vs')[1]?.trim()
              : 'Unknown';
            return {
              id: batch.source_folder || batch.id.toString(),
              teamA: batch.team_name || 'Unknown',
              teamB,
              photoCount: batch.photo_count || 0,
            };
          }),
        })),
      };
    })
    .sort((a, b) => b.year - a.year);
}

export function HierarchicalSidebar({
  pageType,
  rosterEntries = [],
  batches = [],
  onAddGame,
}: HierarchicalSidebarProps) {
  const {
    selectedYear,
    selectedTeam,
    selectedTournament,
    selectedGame,
    setSelectedYear,
    setSelectedTeam,
    setSelectedTournament,
    setSelectedGame,
  } = useSidebar();

  const [expandedYears, setExpandedYears] = useState<Set<number>>(
    new Set(rosterEntries.length > 0 || batches.length > 0 ? [new Date().getFullYear()] : [])
  );
  const [expandedTournaments, setExpandedTournaments] = useState<Set<string>>(new Set());

  const toggleYear = (year: number) => {
    const newExpanded = new Set(expandedYears);
    if (newExpanded.has(year)) {
      newExpanded.delete(year);
    } else {
      newExpanded.add(year);
    }
    setExpandedYears(newExpanded);
  };

  const toggleTournament = (tournament: string) => {
    const newExpanded = new Set(expandedTournaments);
    if (newExpanded.has(tournament)) {
      newExpanded.delete(tournament);
    } else {
      newExpanded.add(tournament);
    }
    setExpandedTournaments(newExpanded);
  };

  if ((pageType === 'roster' || pageType === 'players' || pageType === 'search' || pageType === 'gallery') && rosterEntries.length > 0) {
    const hierarchy = buildRosterHierarchy(rosterEntries);
    return (
      <div className="p-3 space-y-1">
        {hierarchy.map(({ year, teams }) => (
          <div key={year}>
            <button
              onClick={() => toggleYear(year)}
              className="w-full text-left px-3 py-2 rounded-lg hover:bg-muted/40 font-outfit font-bold text-sm text-foreground flex items-center gap-2"
            >
              <span className="text-muted-fg text-xs">{expandedYears.has(year) ? '▼' : '▶'}</span>
              {year}
            </button>
            {expandedYears.has(year) && (
              <div className="ml-3 space-y-0.5">
                {teams.map(({ team, count }) => (
                  <button
                    key={`${year}-${team}`}
                    onClick={() => { setSelectedYear(year); setSelectedTeam(team); }}
                    className={`w-full text-left px-3 py-1.5 rounded-lg font-jakarta text-xs transition-colors ${
                      selectedYear === year && selectedTeam === team
                        ? 'bg-accent/10 text-accent font-semibold border border-accent/20'
                        : 'text-muted-fg hover:bg-muted/40 hover:text-foreground'
                    }`}
                  >
                    {team}
                    <span className="ml-1 opacity-60">({count})</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (pageType === 'upload' || pageType === 'review') {
    const hierarchy = batches.length > 0 ? buildGameHierarchy(batches) : [];
    return (
      <div className="p-3 space-y-1">
        {batches.length === 0 ? (
          <p className="font-jakarta text-xs text-muted-fg text-center py-8 px-3">
            No games yet — save a game context and upload photos.
          </p>
        ) : (
          hierarchy.map(({ year, tournaments }) => (
            <div key={year}>
              <button
                onClick={() => toggleYear(year)}
                className="w-full text-left px-3 py-2 rounded-lg hover:bg-muted/40 font-outfit font-bold text-sm text-foreground flex items-center gap-2"
              >
                <span className="text-muted-fg text-xs">{expandedYears.has(year) ? '▼' : '▶'}</span>
                {year}
              </button>
              {expandedYears.has(year) && (
                <div className="ml-3 space-y-1">
                  {tournaments.map(({ tournament, games }) => (
                    <div key={tournament}>
                      <button
                        onClick={() => toggleTournament(tournament)}
                        className="w-full text-left px-3 py-1.5 rounded-lg hover:bg-muted/40 font-jakarta font-semibold text-xs text-foreground flex items-center gap-2"
                      >
                        <span className="text-muted-fg text-xs">{expandedTournaments.has(tournament) ? '▼' : '▶'}</span>
                        {tournament}
                      </button>
                      {expandedTournaments.has(tournament) && (
                        <div className="ml-3 space-y-0.5">
                          {games.map(({ id, teamA, teamB, photoCount }) => (
                            <button
                              key={id}
                              onClick={() => { setSelectedYear(year); setSelectedTournament(tournament); setSelectedGame(id); }}
                              className={`w-full text-left px-3 py-1.5 rounded-lg font-jakarta text-xs transition-colors ${
                                selectedGame === id
                                  ? 'bg-accent/10 text-accent font-semibold border border-accent/20'
                                  : 'text-muted-fg hover:bg-muted/40 hover:text-foreground'
                              }`}
                            >
                              {teamA} vs {teamB}
                              {photoCount > 0 && <span className="ml-1 opacity-60">({photoCount})</span>}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    );
  }

  return (
    <div className="p-4 font-jakarta text-xs text-muted-fg">
      No data to display
    </div>
  );
}
