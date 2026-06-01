import React, { createContext, useContext, useState, ReactNode } from 'react';

interface SidebarContextType {
  selectedYear: number | null;
  selectedTeam: string | null;
  selectedTournament: string | null;
  selectedGame: string | null;
  setSelectedYear: (year: number | null) => void;
  setSelectedTeam: (team: string | null) => void;
  setSelectedTournament: (tournament: string | null) => void;
  setSelectedGame: (game: string | null) => void;
  clearSelection: () => void;
}

const SidebarContext = createContext<SidebarContextType | undefined>(undefined);

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [selectedTournament, setSelectedTournament] = useState<string | null>(null);
  const [selectedGame, setSelectedGame] = useState<string | null>(null);

  const clearSelection = () => {
    setSelectedYear(null);
    setSelectedTeam(null);
    setSelectedTournament(null);
    setSelectedGame(null);
  };

  const value: SidebarContextType = {
    selectedYear,
    selectedTeam,
    selectedTournament,
    selectedGame,
    setSelectedYear,
    setSelectedTeam,
    setSelectedTournament,
    setSelectedGame,
    clearSelection,
  };

  return (
    <SidebarContext.Provider value={value}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  const context = useContext(SidebarContext);
  if (context === undefined) {
    throw new Error('useSidebar must be used within SidebarProvider');
  }
  return context;
}
