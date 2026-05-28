import React, { useState, useEffect } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import PhotoUpload from '../components/PhotoUpload';
import LoadingSpinner from '../components/LoadingSpinner';
import type { InfoResponse } from '../types/index';

/**
 * UploadPage - Page for uploading photos to the PhotoTagger database
 * Displays upload form and current photo count statistics
 */
export const UploadPage: React.FC = () => {
  const [photoCount, setPhotoCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load photo count on component mount
  useEffect(() => {
    loadPhotoCount();
  }, []);

  const loadPhotoCount = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const info: InfoResponse = await photoTaggerClient.getInfo();
      setPhotoCount(info.total_photos);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load photo count';
      setError(errorMessage);
      setPhotoCount(0);
    } finally {
      setIsLoading(false);
    }
  };

  const handleUploadSuccess = () => {
    loadPhotoCount();
  };

  return (
    <div className="w-full max-w-2xl mx-auto px-4 py-8">
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Upload Photos</h1>
          <p className="mt-2 text-gray-600">
            Add photos from your local directories to the PhotoTagger database
          </p>
        </div>

        <PhotoUpload onUploadSuccess={handleUploadSuccess} />

        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Database Statistics</h2>

          {isLoading ? (
            <div className="flex justify-center py-6">
              <LoadingSpinner message="Loading statistics..." />
            </div>
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-md p-4">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-600">Total Photos in Database:</span>
                <span className="text-2xl font-bold text-blue-600">{photoCount}</span>
              </div>
              <p className="text-xs text-gray-500">
                Updated: {new Date().toLocaleTimeString()}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default UploadPage;
