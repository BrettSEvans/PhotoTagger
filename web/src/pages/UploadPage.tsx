import React, { useState, useEffect, useCallback } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import PhotoUpload from '../components/PhotoUpload';
import LoadingSpinner from '../components/LoadingSpinner';
import type { ProcessingSummary, TaggedPhoto, ReviewPhoto } from '../types/index';

type TabId = 'confirmed' | 'review';

const SHADOW_CLASSES = ['shadow-pop', 'shadow-pop-pink', 'shadow-pop-yellow', 'shadow-pop-mint', 'shadow-pop-violet'];

export const UploadPage: React.FC<{ onOpenWorkspace?: () => void }> = ({ onOpenWorkspace }) => {
  const [summary,       setSummary]       = useState<ProcessingSummary | null>(null);
  const [confirmedPhotos, setConfirmedPhotos] = useState<TaggedPhoto[]>([]);
  const [reviewPhotos,  setReviewPhotos]  = useState<ReviewPhoto[]>([]);
  const [activeTab,     setActiveTab]     = useState<TabId>('confirmed');
  const [isLoadingSum,  setIsLoadingSum]  = useState(true);
  const [isLoadingTab,  setIsLoadingTab]  = useState(false);

  const loadSummary = useCallback(async () => {
    setIsLoadingSum(true);
    try {
      const [sum, confirmed, review] = await Promise.all([
        photoTaggerClient.getProcessingSummary(),
        photoTaggerClient.getConfirmedPhotos(),
        photoTaggerClient.getReviewPhotos(),
      ]);
      setSummary(sum);
      setConfirmedPhotos(confirmed);
      setReviewPhotos(review);
    } catch { /* summary not critical */ }
    finally { setIsLoadingSum(false); }
  }, []);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  const switchTab = async (tab: TabId) => {
    setActiveTab(tab);
    setIsLoadingTab(true);
    try {
      if (tab === 'confirmed') {
        const photos = await photoTaggerClient.getConfirmedPhotos();
        setConfirmedPhotos(photos);
      } else {
        const photos = await photoTaggerClient.getReviewPhotos();
        setReviewPhotos(photos);
      }
    } finally { setIsLoadingTab(false); }
  };

  const confidenceColor = (c: number) => {
    if (c >= 0.7) return 'bg-quaternary';
    if (c >= 0.4) return 'bg-tertiary';
    return 'bg-secondary';
  };

  return (
    <div className="w-full max-w-5xl mx-auto py-4 space-y-6">
      {/* Page header */}
      <div>
        <h1 className="font-outfit text-4xl font-extrabold text-foreground">Upload</h1>
        <p className="mt-2 font-jakarta text-muted-fg">
          Import photos and review auto-tagging results
        </p>
      </div>

      {/* Import form */}
      <PhotoUpload onUploadSuccess={loadSummary} />

      {/* ── Summary Accordion ──────────────────────────────────────────────── */}
      <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg overflow-hidden relative">
        <div aria-hidden="true" className="absolute -top-3 -right-3 w-8 h-8 bg-tertiary rounded-full border-2 border-foreground opacity-80" />

        {isLoadingSum ? (
          <div className="flex justify-center py-8"><LoadingSpinner message="Loading stats…" /></div>
        ) : summary ? (
          <>
            {/* Metric strip */}
            <div className="grid grid-cols-3 divide-x-2 divide-frame border-b-2 border-foreground">
              <div className="px-6 py-5 text-center">
                <p className="font-outfit text-3xl font-extrabold text-foreground">{summary.total_photos}</p>
                <p className="font-jakarta text-xs text-muted-fg mt-1 font-semibold uppercase tracking-wider">Photos</p>
              </div>
              <div className="px-6 py-5 text-center">
                <p className="font-outfit text-3xl font-extrabold text-quaternary">{summary.tagged}</p>
                <p className="font-jakarta text-xs text-muted-fg mt-1 font-semibold uppercase tracking-wider flex items-center justify-center gap-1">
                  <span>Auto-Tagged</span>
                  <svg width="12" height="12" fill="none" stroke="#34D399" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 10 10"><polyline points="1.5,5.5 4,8 8.5,2"/></svg>
                </p>
              </div>
              <div className="px-6 py-5 text-center">
                <p className="font-outfit text-3xl font-extrabold text-secondary">{summary.needs_review}</p>
                <p className="font-jakarta text-xs text-muted-fg mt-1 font-semibold uppercase tracking-wider flex items-center justify-center gap-1">
                  <span>Need Review</span>
                  <span className="text-secondary font-bold">!</span>
                </p>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex border-b-2 border-foreground">
              {([['confirmed', 'Confirmed Tags', summary.tagged], ['review', 'Needs Review', summary.needs_review]] as const).map(
                ([id, label, count]) => (
                  <button
                    key={id}
                    onClick={() => switchTab(id)}
                    className={`flex-1 py-3 font-jakarta font-bold text-sm flex items-center justify-center gap-2 border-r-2 last:border-r-0 border-foreground transition-colors ${
                      activeTab === id
                        ? 'bg-foreground text-white'
                        : 'bg-white text-foreground hover:bg-muted'
                    }`}
                  >
                    {label}
                    <span className={`text-xs px-2 py-0.5 rounded-full font-bold border ${
                      activeTab === id ? 'bg-white text-foreground border-white' : 'bg-muted border-frame text-muted-fg'
                    }`}>
                      {count}
                    </span>
                  </button>
                )
              )}
            </div>

            {/* Tab content */}
            <div className="p-5">
              {isLoadingTab ? (
                <div className="flex justify-center py-8"><LoadingSpinner message="Loading photos…" /></div>
              ) : activeTab === 'confirmed' ? (
                confirmedPhotos.length === 0 ? (
                  <p className="font-jakarta text-sm text-muted-fg text-center py-8">
                    No confirmed tags yet — run OCR from the Upload tab first.
                  </p>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                    {confirmedPhotos.map((photo, i) => (
                      <div key={photo.id} className={`sticker-card bg-white border-2 border-foreground rounded-xl ${SHADOW_CLASSES[i % SHADOW_CLASSES.length]} overflow-hidden`}>
                        <div className="aspect-square bg-muted overflow-hidden relative">
                          <img
                            src={photoTaggerClient.getPhotoUrl(photo.id)}
                            alt={photo.file_path.split('/').pop()}
                            className="w-full h-full object-cover"
                            onError={e => { e.currentTarget.style.display = 'none'; }}
                          />
                          <div className="absolute bottom-0 left-0 right-0 bg-foreground/80 px-2 py-1">
                            <p className="font-outfit font-extrabold text-white text-xs">#{photo.jersey_number}</p>
                          </div>
                        </div>
                        <div className="p-2">
                          <p className="font-jakarta text-xs font-bold text-foreground truncate">{photo.player_name}</p>
                          <div className="mt-1 flex items-center gap-1.5">
                            <div className="flex-1 h-1 bg-muted rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${confidenceColor(photo.confidence)}`} style={{ width: `${Math.min(photo.confidence * 100, 100)}%` }} />
                            </div>
                            <span className="font-jakarta text-xs text-muted-fg">{Math.round(photo.confidence * 100)}%</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              ) : (
                /* Needs Review tab */
                reviewPhotos.length === 0 ? (
                  <p className="font-jakarta text-sm text-muted-fg text-center py-8">
                    No unmatched jerseys — add more players to your roster to reduce this count.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {/* CTA */}
                    {onOpenWorkspace && (
                      <div className="flex items-center justify-between bg-secondary/10 border-2 border-secondary rounded-xl px-4 py-3">
                        <p className="font-jakarta text-sm font-semibold text-foreground">
                          {reviewPhotos.length} photos need manual jersey assignment
                        </p>
                        <button
                          onClick={onOpenWorkspace}
                          className="btn-candy bg-foreground text-white font-jakarta font-bold text-sm px-5 py-2 rounded-full border-2 border-foreground shadow-pop whitespace-nowrap"
                        >
                          Open Cleanup Workspace →
                        </button>
                      </div>
                    )}

                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                      {reviewPhotos.map((photo, i) => (
                        <div key={photo.id} className={`sticker-card bg-white border-2 border-secondary rounded-xl ${SHADOW_CLASSES[i % SHADOW_CLASSES.length]} overflow-hidden`}>
                          <div className="aspect-square bg-muted overflow-hidden relative">
                            <img
                              src={photoTaggerClient.getPhotoUrl(photo.id)}
                              alt={photo.file_path.split('/').pop()}
                              className="w-full h-full object-cover"
                              onError={e => { e.currentTarget.style.display = 'none'; }}
                            />
                            <div className="absolute top-1.5 left-1.5 bg-secondary text-white font-jakarta text-xs font-bold px-1.5 py-0.5 rounded-full">
                              #{photo.jersey_number}
                            </div>
                            <div className="absolute top-1.5 right-1.5 bg-white/90 text-secondary font-jakarta text-xs font-bold px-1.5 py-0.5 rounded-full border border-secondary">
                              !
                            </div>
                          </div>
                          <div className="p-2">
                            <p className="font-jakarta text-xs text-muted-fg truncate">{photo.file_path.split('/').pop()}</p>
                            <p className="font-jakarta text-xs text-muted-fg">{Math.round(photo.confidence * 100)}% conf.</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              )}
            </div>
          </>
        ) : (
          <div className="py-8 text-center">
            <p className="font-jakarta text-sm text-muted-fg">Run OCR to see tagging results</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default UploadPage;
