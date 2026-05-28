import React from 'react';

interface ConfidenceBadgeProps {
  confidence: number;
  label?: string;
}

/**
 * ConfidenceBadge - Displays confidence percentage with color-coded styling
 * Colors: red (<50%), orange (50-79%), green (>=80%)
 */
export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
  confidence,
  label,
}) => {
  const percentage = Math.round(confidence * 100);

  let bgColor = '';
  let textColor = '';

  if (percentage < 50) {
    bgColor = 'bg-red-100';
    textColor = 'text-red-800';
  } else if (percentage < 80) {
    bgColor = 'bg-orange-100';
    textColor = 'text-orange-800';
  } else {
    bgColor = 'bg-green-100';
    textColor = 'text-green-800';
  }

  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full ${bgColor}`}>
      {label && <span className={`text-xs font-medium ${textColor}`}>{label}</span>}
      <span className={`text-sm font-semibold ${textColor}`}>{percentage}%</span>
    </div>
  );
};

export default ConfidenceBadge;
