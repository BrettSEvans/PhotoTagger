import React, { useState } from 'react';
import { IdentifiedPlayer } from '../types';
import { ConfidenceBadge } from './ConfidenceBadge';

interface PlayerCardProps {
  player: IdentifiedPlayer;
  photoPath?: string;
}

/**
 * PlayerCard - Displays identified player information with expandable details
 * Shows jersey, team, location, and individual confidence scores
 */
export const PlayerCard: React.FC<PlayerCardProps> = ({ player, photoPath }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const locationLabel = {
    field: 'On Field',
    sideline: 'Sideline',
    background: 'Background',
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-shadow">
      {photoPath && (
        <div className="w-full h-48 bg-gray-200 rounded-t-lg overflow-hidden">
          <img
            src={photoPath}
            alt="Player photo"
            className="w-full h-full object-cover"
          />
        </div>
      )}

      <div className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div>
            {player.player_name && (
              <h3 className="text-lg font-semibold text-gray-900">
                {player.player_name}
              </h3>
            )}
            {player.jersey_number && (
              <p className="text-2xl font-bold text-blue-600">
                #{player.jersey_number}
              </p>
            )}
          </div>
          <ConfidenceBadge
            confidence={player.combined_confidence}
            label="Combined"
          />
        </div>

        <div className="space-y-2 mb-4">
          {player.team_name && (
            <p className="text-sm text-gray-600">
              <span className="font-medium">Team:</span> {player.team_name}
              {player.team_year && ` (${player.team_year})`}
            </p>
          )}
          <p className="text-sm text-gray-600">
            <span className="font-medium">Color:</span>
            <span
              className="inline-block w-4 h-4 rounded-full ml-2 border border-gray-300 align-middle"
              style={{ backgroundColor: player.color }}
              title={player.color}
            />
            {player.color}
          </p>
          <p className="text-sm text-gray-600">
            <span className="font-medium">Location:</span>{' '}
            {locationLabel[player.location]}
          </p>
        </div>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium"
        >
          {isExpanded ? 'Hide Details' : 'Show Details'}
        </button>

        {isExpanded && (
          <div className="mt-4 pt-4 border-t border-gray-200 space-y-2">
            <h4 className="font-semibold text-sm text-gray-700 mb-3">
              Confidence Breakdown
            </h4>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <div>
                <ConfidenceBadge
                  confidence={player.jersey_confidence}
                  label="Jersey"
                />
              </div>
              <div>
                <ConfidenceBadge
                  confidence={player.color_confidence}
                  label="Color"
                />
              </div>
              <div>
                <ConfidenceBadge
                  confidence={player.location_confidence}
                  label="Location"
                />
              </div>
              <div>
                <ConfidenceBadge
                  confidence={player.combined_confidence}
                  label="Overall"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default PlayerCard;
