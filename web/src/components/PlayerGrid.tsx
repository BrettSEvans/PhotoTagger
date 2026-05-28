import React from 'react';
import { IdentifiedPlayer } from '../types';
import { PlayerCard } from './PlayerCard';
import { LoadingSpinner } from './LoadingSpinner';

interface PlayerGridProps {
  players: IdentifiedPlayer[];
  isLoading?: boolean;
  photoPath?: string;
}

/**
 * PlayerGrid - Displays a responsive grid of identified players
 * Shows PlayerCard components for each player with loading and empty states
 */
export const PlayerGrid: React.FC<PlayerGridProps> = ({
  players,
  isLoading = false,
  photoPath,
}) => {
  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-12">
        <LoadingSpinner message="Searching for players..." />
      </div>
    );
  }

  if (players.length === 0) {
    return (
      <div className="flex justify-center items-center py-12">
        <p className="text-gray-500 text-lg">No players found matching your criteria</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {players.map((player, index) => (
        <PlayerCard key={index} player={player} photoPath={photoPath} />
      ))}
    </div>
  );
};

export default PlayerGrid;
