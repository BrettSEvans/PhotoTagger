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
      <div className="p-4 space-y-2">
        {hierarchy.map(({ year, teams }) => (
          <div key={year}>
            <button
              onClick={() => toggleYear(year)}
              className="w-full text-left px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2"
            >
              <span className="text-gray-600 dark:text-gray-400">
                {expandedYears.has(year) ? '▼' : '▶'}
              </span>
              Year {year}
            </button>
            {expandedYears.has(year) && (
              <div className="ml-4 space-y-1">
                {teams.map(({ team, count }) => (
                  <button
                    key={`${year}-${team}`}
                    onClick={() => {
                      setSelectedYear(year);
                      setSelectedTeam(team);
                    }}
                    className={`w-full text-left px-3 py-2 rounded text-sm ${
                      selectedYear === year && selectedTeam === team
                        ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100 font-semibold'
                        : 'hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    {team} ({count})
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
      <div className="p-4 space-y-3">
        {pageType === 'upload' && (
          <button
            onClick={onAddGame}
            className="w-full bg-blue-500 hover:bg-blue-600 text-white font-semibold py-2 px-3 rounded text-sm"
          >
            + Add Game
          </button>
        )}
        {batches.length === 0 ? (
          <div className="text-gray-600 dark:text-gray-400 text-sm text-center py-8">
            No games yet
          </div>
        ) : (
          hierarchy.map(({ year, tournaments }) => (
          <div key={year}>
            <button
              onClick={() => toggleYear(year)}
              className="w-full text-left px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2"
            >
              <span className="text-gray-600 dark:text-gray-400">
                {expandedYears.has(year) ? '▼' : '▶'}
              </span>
              Year {year}
            </button>
            {expandedYears.has(year) && (
              <div className="ml-4 space-y-2">
                {tournaments.map(({ tournament, games }) => (
                  <div key={tournament}>
                    <button
                      onClick={() => toggleTournament(tournament)}
                      className="w-full text-left px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2"
                    >
                      <span className="text-gray-600 dark:text-gray-400">
                        {expandedTournaments.has(tournament) ? '▼' : '▶'}
                      </span>
                      {tournament}
                    </button>
                    {expandedTournaments.has(tournament) && (
                      <div className="ml-4 space-y-1">
                        {games.map(({ id, teamA, teamB, photoCount }) => (
                          <button
                            key={id}
                            onClick={() => {
                              setSelectedYear(year);
                              setSelectedTournament(tournament);
                              setSelectedGame(id);
                            }}
                            className={`w-full text-left px-3 py-2 rounded text-sm ${
                              selectedGame === id
                                ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100 font-semibold'
                                : 'hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                            }`}
                          >
                            {teamA} vs {teamB} ({photoCount})
                          </button>
                        ))}
                        {pageType === 'upload' && (
                          <button
                            onClick={() => {
                              setSelectedYear(year);
                              setSelectedTournament(tournament);
                              setSelectedGame(null);
                              onAddGame?.();
                            }}
                            className="w-full text-left px-3 py-2 rounded text-sm text-blue-600 dark:text-blue-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                          >
                            + Add Game
                          </button>
                        )}
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
    <div className="p-4 text-gray-600 dark:text-gray-400 text-sm">
      No data to display
    </div>
  );
}
