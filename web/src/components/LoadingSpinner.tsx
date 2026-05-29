import React from 'react';

interface LoadingSpinnerProps {
  message?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  message = 'Loading...',
}) => {
  return (
    <div role="status" aria-label={message} className="flex flex-col items-center justify-center gap-3">
      <div className="relative w-12 h-12">
        {/* Outer hard-shadow ring */}
        <div className="absolute inset-0 rounded-full border-2 border-foreground bg-accent shadow-pop" />
        {/* Spinning arc */}
        <div className="absolute inset-0 rounded-full border-[3px] border-transparent border-t-white animate-spin" />
      </div>
      {message && (
        <p className="font-jakarta text-sm font-medium text-muted-fg">{message}</p>
      )}
    </div>
  );
};

export default LoadingSpinner;
