import React, { useRef } from 'react';

interface SelectPhotosCardProps {
  selectedFiles: File[];
  uploadMode: 'files' | 'directory';
  photoDirectory: string;
  isDragging: boolean;
  message: { type: 'success' | 'error'; text: string } | null;
  isLoading: boolean;
  onFilesSelected: (files: File[]) => void;
  onModeChange: (mode: 'files' | 'directory') => void;
  onDirectoryChange: (path: string) => void;
  onClear: () => void;
  onDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void;
}

export const SelectPhotosCard: React.FC<SelectPhotosCardProps> = ({
  selectedFiles,
  uploadMode,
  photoDirectory,
  isDragging,
  message,
  isLoading,
  onFilesSelected,
  onModeChange,
  onDirectoryChange,
  onClear,
  onDragOver,
  onDragLeave,
  onDrop,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const isImageFile = (file: File): boolean => {
    return file.type.startsWith('image/');
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const imageFiles = files.filter(isImageFile);

    if (imageFiles.length === 0) {
      return;
    }

    onFilesSelected(imageFiles);
    e.target.value = '';
  };

  const handleSelectPhotos = () => {
    fileInputRef.current?.click();
  };

  const handleSelectFolder = () => {
    folderInputRef.current?.click();
  };

  return (
    <div className="w-full bg-white border-2 border-foreground rounded-2xl shadow-pop-lg p-6 relative">
      {/* Floating accent dot */}
      <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-tertiary rounded-full border-2 border-foreground" />

      <div className="mb-5">
        <div className="flex items-center gap-2 mb-2">
          <span className="font-outfit text-lg font-bold text-foreground">1.</span>
          <h2 className="font-outfit text-xl font-bold text-foreground">Select Photos</h2>
        </div>
      </div>

      {/* Upload mode toggle */}
      <div className="flex gap-2 mb-4">
        <button
          type="button"
          onClick={() => {
            onModeChange('files');
            onDirectoryChange('');
          }}
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
          onClick={() => {
            onModeChange('directory');
            onClear();
          }}
          className={`px-4 py-2 rounded-full border-2 font-jakarta text-sm font-semibold transition-colors ${
            uploadMode === 'directory'
              ? 'bg-accent text-white border-foreground'
              : 'bg-white text-foreground border-frame hover:bg-quaternary/5'
          }`}
        >
          📂 From Directory
        </button>
      </div>

      {/* File Upload Mode */}
      {uploadMode === 'files' && (
        <>
          {/* Drop zone */}
          <div
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
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
            {/* Hidden file input for folder selection */}
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
            <div className="mt-4 bg-quaternary/5 border-2 border-quaternary rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <p className="font-jakarta text-sm font-semibold text-foreground">
                  {selectedFiles.length} file{selectedFiles.length !== 1 ? 's' : ''} selected
                </p>
                <button
                  type="button"
                  onClick={onClear}
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
        </>
      )}

      {/* Directory Upload Mode */}
      {uploadMode === 'directory' && (
        <div className="space-y-3">
          <label className="block">
            <p className="font-jakarta text-sm font-semibold text-foreground mb-2">Photo Directory Path</p>
            <input
              type="text"
              value={photoDirectory}
              onChange={(e) => onDirectoryChange(e.target.value)}
              placeholder="/path/to/your/photos"
              disabled={isLoading}
              className="w-full px-4 py-2 border-2 border-frame rounded-lg font-jakarta text-sm focus:outline-none focus:border-accent"
            />
            <p className="font-jakarta text-xs text-muted-fg mt-2">
              Enter the absolute path to your photos directory
            </p>
          </label>
        </div>
      )}

      {/* Message display */}
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

export default SelectPhotosCard;
