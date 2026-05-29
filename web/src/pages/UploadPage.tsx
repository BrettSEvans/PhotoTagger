import React, { useState, useEffect } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import PhotoUpload from '../components/PhotoUpload';
import LoadingSpinner from '../components/LoadingSpinner';
import type { InfoResponse } from '../types/index';

export const UploadPage: React.FC = () => {
  const [photoCount, setPhotoCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { loadPhotoCount(); }, []);

  const loadPhotoCount = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const info: InfoResponse = await photoTaggerClient.getInfo();
      setPhotoCount(info.total_photos);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load photo count');
      setPhotoCount(0);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto py-4 space-y-6">
      {/* Page header */}
      <div>
        <h1 className="font-outfit text-4xl font-extrabold text-foreground">
          Upload Photos
        </h1>
        <p className="mt-2 font-jakarta text-muted-fg">
          Point PhotoTagger at a folder to import your tournament shots
        </p>
      </div>

      <PhotoUpload onUploadSuccess={loadPhotoCount} />

      {/* Stats card */}
      <div className="relative bg-white border-2 border-foreground rounded-2xl shadow-pop-yellow p-6 overflow-hidden">
        {/* Yellow background accent strip */}
        <div aria-hidden="true" className="absolute inset-y-0 left-0 w-2 bg-tertiary" />
        <div aria-hidden="true" className="absolute -top-4 -right-4 w-12 h-12 bg-tertiary rounded-full border-2 border-foreground opacity-60" />

        <h2 className="font-outfit text-lg font-bold text-foreground mb-4 pl-3">Library Stats</h2>

        {isLoading ? (
          <div className="flex justify-center py-4">
            <LoadingSpinner message="Loading…" />
          </div>
        ) : error ? (
          <p className="font-jakarta text-sm text-secondary">{error}</p>
        ) : (
          <div className="flex items-end gap-3 pl-3">
            <span className="font-outfit text-6xl font-extrabold text-foreground leading-none">{photoCount}</span>
            <span className="font-jakarta text-muted-fg font-medium mb-1">photos in database</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default UploadPage;
