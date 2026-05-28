import React from 'react';

interface LoadingSpinnerProps {
  message?: string;
}

/**
 * LoadingSpinner - Animated loading indicator with optional message
 * Uses Tailwind CSS animate-spin for the spinner animation
 */
export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  message = 'Loading...',
}) => {
  return (
    <div className="flex flex-col items-center justify-center gap-4">
      <div className="w-12 h-12 border-4 border-gray-300 border-t-blue-500 rounded-full animate-spin" />
      {message && <p className="text-gray-600 text-sm">{message}</p>}
    </div>
  );
};

export default LoadingSpinner;
