import React, { useState } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from './LoadingSpinner';

interface PhotoUploadProps {
  onUploadSuccess?: () => void;
}

/**
 * PhotoUpload - Form component for crawling and uploading photos from a directory
 * Displays upload status and results with error handling
 */
export const PhotoUpload: React.FC<PhotoUploadProps> = ({ onUploadSuccess }) => {
  const [photoDir, setPhotoDir] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!photoDir.trim()) {
      setMessage({
        type: 'error',
        text: 'Please enter a photo directory path',
      });
      return;
    }

    setIsLoading(true);
    setMessage(null);

    try {
      const response = await photoTaggerClient.crawlPhotos(photoDir.trim());

      if (response.success) {
        const { added, skipped } = response.results;
        setMessage({
          type: 'success',
          text: `Uploaded ${added} photos (${skipped} duplicates)`,
        });
        setPhotoDir('');

        if (onUploadSuccess) {
          onUploadSuccess();
        }
      } else {
        setMessage({
          type: 'error',
          text: 'Upload failed. Please try again.',
        });
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to upload photos';
      setMessage({
        type: 'error',
        text: errorMessage,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full bg-white border border-gray-200 rounded-lg shadow-sm p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Upload Photos</h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="photoDir" className="block text-sm font-medium text-gray-700 mb-2">
            Photo Directory Path
          </label>
          <input
            id="photoDir"
            type="text"
            value={photoDir}
            onChange={(e) => setPhotoDir(e.target.value)}
            placeholder="e.g., /path/to/photos"
            disabled={isLoading}
            className="w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:text-gray-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            Enter the full path to a directory containing photo files
          </p>
        </div>

        <button
          type="submit"
          disabled={isLoading || !photoDir.trim()}
          className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium rounded-md transition-colors"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Uploading...
            </span>
          ) : (
            'Upload Photos'
          )}
        </button>
      </form>

      {isLoading && (
        <div className="mt-6 flex justify-center">
          <LoadingSpinner message="Processing photos..." />
        </div>
      )}

      {message && (
        <div
          className={`mt-4 p-4 rounded-md ${
            message.type === 'success'
              ? 'bg-green-50 border border-green-200'
              : 'bg-red-50 border border-red-200'
          }`}
        >
          <p
            className={`text-sm font-medium ${
              message.type === 'success' ? 'text-green-800' : 'text-red-800'
            }`}
          >
            {message.text}
          </p>
        </div>
      )}
    </div>
  );
};

export default PhotoUpload;
