import React, { useState, useEffect } from 'react';
import LoadingSpinner from '../components/LoadingSpinner';
import photoTaggerClient from '../api/photoTaggerClient';
import type { PhotoItem } from '../types/index';

/**
 * GalleryPage - Photo gallery view for browsing all uploaded photos
 * Displays photos in a grid layout with loading and empty states
 * Note: Currently uses placeholder data. Will integrate with /api/photos endpoint in Task 7.
 */
export const GalleryPage: React.FC = () => {
  const [photos, setPhotos] = useState<PhotoItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load photos on component mount
  useEffect(() => {
    loadPhotos();
  }, []);

  const loadPhotos = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await photoTaggerClient.getPhotos(1, 20);
      setPhotos(result.photos);
    } catch (error) {
      console.error('Failed to load photos:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to load photos';
      setError(errorMessage);
      setPhotos([]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-6xl mx-auto px-4 py-8">
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Photo Gallery</h1>
          <p className="mt-2 text-gray-600">
            Browse all uploaded photos in the PhotoTagger database
          </p>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner message="Loading photos..." />
          </div>
        ) : error ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-6">
            <p className="text-sm font-medium text-red-800">{error}</p>
          </div>
        ) : photos.length === 0 ? (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-12 text-center">
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
            <h3 className="mt-4 text-lg font-medium text-gray-900">No photos yet</h3>
            <p className="mt-1 text-gray-600">
              Upload photos from the Upload page to get started
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {photos.map((photo) => (
              <div
                key={photo.id}
                className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow"
              >
                <div className="aspect-square bg-gray-100 flex items-center justify-center">
                  <svg
                    className="h-12 w-12 text-gray-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                    />
                  </svg>
                </div>
                <div className="p-4">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {photo.filename}
                  </p>
                  <p className="mt-1 text-xs text-gray-500">
                    {new Date(photo.added_at).toLocaleDateString()}
                  </p>
                  <p className="mt-2 text-xs text-gray-400">
                    Path: {photo.path}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default GalleryPage;
