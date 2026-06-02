import React, { useState, useRef } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from './LoadingSpinner';
import type { CrawlResult } from '../types/index';

interface PhotoUploadProps {
  onUploadSuccess?: () => void;
}

export const PhotoUpload: React.FC<PhotoUploadProps> = ({ onUploadSuccess }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const dropZoneRef = useRef<HTMLDivElement>(null);

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [photoDirectory, setPhotoDirectory] = useState<string>('');
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [uploadMode, setUploadMode] = useState<'files' | 'directory'>('files');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Validate that file is an image
  const isImageFile = (file: File): boolean => {
    return file.type.startsWith('image/');
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    const imageFiles = files.filter(isImageFile);

    if (imageFiles.length === 0) {
      setMessage({
        type: 'error',
        text: 'Please drop image files only (JPG, PNG, TIFF, HEIC, WebP)',
      });
      return;
    }

    setSelectedFiles(imageFiles);
    setMessage(null);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const imageFiles = files.filter(isImageFile);

    if (imageFiles.length === 0) {
      setMessage({
        type: 'error',
        text: 'Please select image files only',
      });
      return;
    }

    setSelectedFiles(imageFiles);
    setMessage(null);

    // Clear input to allow re-selection of same file
    e.target.value = '';
  };

  const handleSelectPhotos = () => {
    fileInputRef.current?.click();
  };

  const handleSelectFolder = () => {
    folderInputRef.current?.click();
  };

  const handleClearSelection = () => {
    setSelectedFiles([]);
    setMessage(null);
  };

  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (uploadMode === 'files' && selectedFiles.length === 0) {
      setMessage({ type: 'error', text: 'Please select at least one photo' });
      return;
    }

    if (uploadMode === 'directory' && !photoDirectory.trim()) {
      setMessage({ type: 'error', text: 'Please enter a photo directory path' });
      return;
    }

    setIsLoading(true);
    setMessage(null);

    try {
      let response;

      if (uploadMode === 'files') {
        // Upload files
        const formData = new FormData();
        selectedFiles.forEach(file => {
          formData.append('files', file);
        });
        response = await photoTaggerClient.uploadPhotos(formData);
      } else {
        // Upload from directory
        response = await photoTaggerClient.crawlPhotos(photoDirectory.trim());
      }

      setMessage({ type: 'success', text: 'Upload started. Processing photos…' });

      // Poll job status
      const job = await photoTaggerClient.pollJob<CrawlResult>(response.job_id, {
        onUpdate: currentJob => {
          if (currentJob.status === 'queued') {
            setMessage({ type: 'success', text: 'Processing queued…' });
          } else if (currentJob.status === 'running') {
            setMessage({ type: 'success', text: `Processing… ${currentJob.progress}%` });
          }
        },
      });

      const result = job.result;
      if (!result) {
        throw new Error('Upload finished without a result');
      }

      setMessage({
        type: 'success',
        text: `Added ${result.photos_ingested} photos · ${result.duplicates_skipped} duplicates skipped`,
      });
      setSelectedFiles([]);
      setPhotoDirectory('');
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

      {/* Upload mode toggle */}
      <div className="flex gap-2 mb-4">
        <button
          type="button"
          onClick={() => { setUploadMode('files'); setPhotoDirectory(''); }}
          className={`px-4 py-2 rounded-full border-2 font-jakarta text-sm font-semibold transition-colors ${
            uploadMode === 'files'
              ? 'bg-accent text-white border-foreground'
              : 'bg-white text-foreground border-frame hover:bg-quaternary/5'
          }`}
        >
          📁 Upload Files
        </button>
        <button
          type="button"
          onClick={() => { setUploadMode('directory'); setSelectedFiles([]); }}
          className={`px-4 py-2 rounded-full border-2 font-jakarta text-sm font-semibold transition-colors ${
            uploadMode === 'directory'
              ? 'bg-accent text-white border-foreground'
              : 'bg-white text-foreground border-frame hover:bg-quaternary/5'
          }`}
        >
          📂 From Directory
        </button>
      </div>

      <form onSubmit={handleUpload} className="space-y-4">
        {/* File Upload Mode */}
        {uploadMode === 'files' && (
          <>
        {/* Drop zone */}
        <div
          ref={dropZoneRef}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
            isDragging
              ? 'border-accent bg-accent/10'
              : 'border-frame bg-white hover:bg-quaternary/5'
          }`}
        >
          <div className="flex flex-col items-center gap-3">
            <div className="text-3xl">📸</div>
            <p className="font-jakarta text-sm font-semibold text-foreground">
              {isDragging ? 'Drop photos here' : 'Drag photos here or'}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleSelectPhotos}
                disabled={isLoading}
                className="btn-candy px-4 py-2 bg-accent text-white border-2 border-foreground rounded-full font-jakarta text-sm font-bold hover:opacity-90 disabled:opacity-50"
              >
                Select Photos
              </button>
              <button
                type="button"
                onClick={handleSelectFolder}
                disabled={isLoading}
                className="btn-candy px-4 py-2 bg-tertiary text-white border-2 border-foreground rounded-full font-jakarta text-sm font-bold hover:opacity-90 disabled:opacity-50"
              >
                Select Folder
              </button>
            </div>
            <p className="font-jakarta text-xs text-muted-fg mt-2">
              Supports: JPG, PNG, TIFF, HEIC, WebP
            </p>
          </div>

          {/* Hidden file input for individual files */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*"
            onChange={handleFileSelect}
            className="hidden"
            disabled={isLoading}
          />
          {/* Hidden file input for folder selection.
              webkitdirectory must be set imperatively — React strips the bare JSX attribute. */}
          <input
            ref={(el) => {
              folderInputRef.current = el;
              if (el) {
                el.setAttribute('webkitdirectory', '');
                el.setAttribute('directory', '');
              }
            }}
            type="file"
            multiple
            accept="image/*"
            onChange={handleFileSelect}
            className="hidden"
            disabled={isLoading}
          />
        </div>

        {/* File list */}
        {selectedFiles.length > 0 && (
          <div className="bg-quaternary/5 border-2 border-quaternary rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="font-jakarta text-sm font-semibold text-foreground">
                {selectedFiles.length} file{selectedFiles.length !== 1 ? 's' : ''} selected
              </p>
              <button
                type="button"
                onClick={handleClearSelection}
                disabled={isLoading}
                className="text-xs font-jakarta text-muted-fg hover:text-foreground disabled:opacity-50"
              >
                Clear
              </button>
            </div>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {selectedFiles.map((file, idx) => (
                <p key={idx} className="font-jakarta text-xs text-foreground truncate">
                  • {file.name}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* Upload button for files */}
        <button
          type="submit"
          disabled={isLoading || selectedFiles.length === 0}
          className="btn-candy w-full bg-accent text-white font-jakarta font-bold px-6 py-3 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Uploading…
            </span>
          ) : 'Upload Photos'}
        </button>
        </>
        )}

        {uploadMode === 'directory' && (
        <>
        {/* Directory path input */}
        <div className="space-y-3">
          <label className="block">
            <p className="font-jakarta text-sm font-semibold text-foreground mb-2">Photo Directory Path</p>
            <input
              type="text"
              value={photoDirectory}
              onChange={(e) => setPhotoDirectory(e.target.value)}
              placeholder="/path/to/your/photos"
              disabled={isLoading}
              className="w-full px-4 py-2 border-2 border-frame rounded-lg font-jakarta text-sm focus:outline-none focus:border-accent"
            />
            <p className="font-jakarta text-xs text-muted-fg mt-2">
              Enter the absolute path to your photos directory
            </p>
          </label>
        </div>

        {/* Upload button */}
        <button
          type="submit"
          disabled={isLoading || !photoDirectory.trim()}
          className="btn-candy w-full bg-accent text-white font-jakarta font-bold px-6 py-3 rounded-full border-2 border-foreground shadow-pop disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Importing…
            </span>
          ) : 'Import Photos'}
        </button>
        </>
        )}
      </form>

      {isLoading && (
        <div className="mt-6 flex justify-center">
          <LoadingSpinner message="Processing photos…" />
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
          }`}
        >
          <span className="mr-2">{message.type === 'success' ? '✅' : '⚠️'}</span>
          {message.text}
        </div>
      )}
    </div>
  );
};

export default PhotoUpload;
