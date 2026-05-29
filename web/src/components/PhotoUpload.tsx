import React, { useState } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from './LoadingSpinner';
import type { CrawlResult } from '../types/index';

interface PhotoUploadProps {
  onUploadSuccess?: () => void;
}

export const PhotoUpload: React.FC<PhotoUploadProps> = ({ onUploadSuccess }) => {
  const [photoDir, setPhotoDir] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isPicking, setIsPicking] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleBrowse = async () => {
    setIsPicking(true);
    try {
      const path = await photoTaggerClient.pickDirectory();
      if (path) {
        setPhotoDir(path);
        setMessage(null);
      }
    } catch {
      setMessage({ type: 'error', text: 'Could not open directory picker' });
    } finally {
      setIsPicking(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!photoDir.trim()) {
      setMessage({ type: 'error', text: 'Please enter a photo directory path' });
      return;
    }
    setIsLoading(true);
    setMessage(null);
    try {
      const response = await photoTaggerClient.crawlPhotos(photoDir.trim());
      setMessage({ type: 'success', text: 'Import started. Scanning photos…' });
      const job = await photoTaggerClient.pollJob<CrawlResult>(response.job_id, {
        onUpdate: currentJob => {
          if (currentJob.status === 'queued') {
            setMessage({ type: 'success', text: 'Import queued…' });
          } else if (currentJob.status === 'running') {
            setMessage({ type: 'success', text: `Scanning photos… ${currentJob.progress}%` });
          }
        },
      });

      const result = job.result;
      if (!result) {
        throw new Error('Import finished without a result');
      }

      setMessage({
        type: 'success',
        text: `Added ${result.photos_ingested} photos · ${result.duplicates_skipped} duplicates skipped`,
      });
      setPhotoDir('');
      onUploadSuccess?.();
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to upload photos' });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full bg-white border-2 border-foreground rounded-2xl shadow-pop-lg p-6 relative">
      {/* Floating accent dot */}
      <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-tertiary rounded-full border-2 border-foreground" />

      <h2 className="font-outfit text-xl font-bold text-foreground mb-5">Add Photos</h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="photoDir" className="block font-jakarta text-xs font-bold uppercase tracking-wider text-foreground mb-2">
            Photo Directory
          </label>
          <div className="flex gap-2">
            <input
              id="photoDir"
              type="text"
              value={photoDir}
              onChange={(e) => setPhotoDir(e.target.value)}
              placeholder="/path/to/your/photos"
              disabled={isLoading || isPicking}
              className="geo-input flex-1 px-4 py-2.5 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground placeholder:text-muted-fg disabled:bg-muted disabled:text-muted-fg"
            />
            <button
              type="button"
              onClick={handleBrowse}
              disabled={isLoading || isPicking}
              className="btn-candy px-4 py-2.5 bg-white border-2 border-foreground rounded-full shadow-pop-sm font-jakarta text-sm font-bold text-foreground disabled:opacity-50 whitespace-nowrap hover:bg-tertiary"
            >
              {isPicking ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-foreground border-t-transparent rounded-full animate-spin" />
                  Opening…
                </span>
              ) : '📁 Browse'}
            </button>
          </div>
          <p className="mt-1.5 font-jakarta text-xs text-muted-fg">Browse to select a folder or paste a path directly</p>
        </div>

        <button
          type="submit"
          disabled={isLoading || !photoDir.trim()}
          className="btn-candy w-full bg-accent text-white font-jakarta font-bold px-6 py-3 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Importing photos…
            </span>
          ) : 'Import Photos'}
        </button>
      </form>

      {isLoading && (
        <div className="mt-6 flex justify-center">
          <LoadingSpinner message="Scanning directory…" />
        </div>
      )}

      {message && (
        <div
          role={message.type === 'error' ? 'alert' : 'status'}
          aria-live={message.type === 'error' ? 'assertive' : 'polite'}
          className={`mt-4 p-4 rounded-xl border-2 font-jakarta text-sm font-medium ${
          message.type === 'success'
            ? 'bg-quaternary/10 border-quaternary text-foreground'
            : 'bg-secondary/10 border-secondary text-foreground'
        }`}>
          <span className="mr-2">{message.type === 'success' ? '✅' : '⚠️'}</span>
          {message.text}
        </div>
      )}
    </div>
  );
};

export default PhotoUpload;
