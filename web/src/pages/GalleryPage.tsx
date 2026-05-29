import React, { useState, useEffect } from 'react';
import LoadingSpinner from '../components/LoadingSpinner';
import photoTaggerClient from '../api/photoTaggerClient';
import type { PhotoItem } from '../types/index';

const PAGE_SIZE = 40;

// Rotate pop-shadow colors for a confetti effect across the grid
const SHADOW_CLASSES = [
  'shadow-pop',
  'shadow-pop-pink',
  'shadow-pop-yellow',
  'shadow-pop-mint',
  'shadow-pop-violet',
];

export const GalleryPage: React.FC = () => {
  const [photos, setPhotos] = useState<PhotoItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  useEffect(() => { loadPhotos(1); }, []);

  const loadPhotos = async (pageNum: number) => {
    const isFirst = pageNum === 1;
    isFirst ? setIsLoading(true) : setIsLoadingMore(true);
    setError(null);
    try {
      const result = await photoTaggerClient.getPhotos(pageNum, PAGE_SIZE);
      setTotal(result.total);
      setPhotos(prev => isFirst ? result.photos : [...prev, ...result.photos]);
      setPage(pageNum);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to load photos');
    } finally {
      isFirst ? setIsLoading(false) : setIsLoadingMore(false);
    }
  };

  return (
    <div className="w-full max-w-6xl mx-auto py-4 space-y-6">
      <div>
        <h1 className="font-outfit text-4xl font-extrabold text-foreground">Gallery</h1>
        <p className="mt-2 font-jakarta text-muted-fg">
          {total > 0 ? `${photos.length} of ${total} photos` : 'Browse all imported photos'}
        </p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <LoadingSpinner message="Loading photos…" />
        </div>
      ) : error ? (
        <div role="alert" className="bg-white border-2 border-secondary rounded-2xl shadow-pop-pink p-6">
          <p className="font-jakarta text-sm font-medium text-foreground">⚠️ {error}</p>
          <button
            onClick={() => loadPhotos(1)}
            className="btn-candy mt-3 bg-accent text-white font-jakarta font-bold px-5 py-2 rounded-full border-2 border-foreground shadow-pop text-sm"
          >
            Retry
          </button>
        </div>
      ) : photos.length === 0 ? (
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg p-14 text-center relative overflow-hidden">
          <div aria-hidden="true" className="absolute -top-5 -right-5 w-14 h-14 bg-tertiary rounded-full border-2 border-foreground opacity-70" />
          <div aria-hidden="true" className="absolute -bottom-4 -left-4 w-10 h-10 bg-secondary rotate-12 border-2 border-foreground opacity-50" />
          <div className="w-10 h-10 bg-muted rounded-xl border-2 border-foreground mx-auto flex items-center justify-center mb-4">
            <svg className="h-5 w-5 text-muted-fg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
            </svg>
          </div>
          <h3 className="font-outfit text-xl font-bold text-foreground">No photos yet</h3>
          <p className="mt-1 font-jakarta text-muted-fg">Import photos from the Upload tab to get started</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {photos.map((photo, i) => (
              <div
                key={photo.id}
                className={`sticker-card bg-white border-2 border-foreground rounded-xl ${SHADOW_CLASSES[i % SHADOW_CLASSES.length]} overflow-hidden`}
              >
                <div className="aspect-square bg-muted overflow-hidden">
                  <img
                    src={`http://127.0.0.1:5001/api/image/${photo.id}`}
                    alt={photo.filename}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      const target = e.currentTarget;
                      target.style.display = 'none';
                      const parent = target.parentElement;
                      if (parent && !parent.querySelector('svg')) {
                        parent.innerHTML = `<div class="w-full h-full flex items-center justify-center bg-muted"><svg class="h-10 w-10 color-muted-fg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909"/></svg></div>`;
                      }
                    }}
                  />
                </div>
                <div className="p-2.5">
                  <p className="font-jakarta text-xs font-semibold text-foreground truncate">{photo.filename}</p>
                  <p className="font-jakarta text-xs text-muted-fg mt-0.5">
                    {(() => {
                      const d = new Date(photo.added_at);
                      return !isNaN(d.getTime()) ? d.toLocaleDateString() : '—';
                    })()}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {photos.length < total && (
            <div className="flex justify-center pt-2">
              <button
                onClick={() => loadPhotos(page + 1)}
                disabled={isLoadingMore}
                className="btn-candy bg-white font-jakarta font-bold px-8 py-3 rounded-full border-2 border-foreground shadow-pop disabled:opacity-50 text-foreground hover:bg-tertiary"
              >
                {isLoadingMore ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-foreground border-t-transparent rounded-full animate-spin" />
                    Loading…
                  </span>
                ) : `Load more · ${total - photos.length} remaining`}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default GalleryPage;
