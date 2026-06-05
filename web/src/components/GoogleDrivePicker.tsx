import React, { useCallback, useEffect, useRef, useState } from 'react';

/* ─────────────────────────────────────────────────────────────────
   GoogleDrivePicker

   Fetches the app's Google Client ID from the backend at
   GET /api/app-config so end-users never need to touch credentials.

   Flow:
     1. On mount: fetch /api/app-config → google_client_id
     2. User clicks "Sign in with Google"
     3. Google OAuth consent popup (drive.readonly scope)
     4. Google Folder Picker popup
     5. Enumerate images in the selected folder (Drive API v3)
     6. Download each image → File[]
     7. Call onFilesReady(files)  ← parent handles upload as normal
───────────────────────────────────────────────────────────────── */

const SCOPE = 'https://www.googleapis.com/auth/drive.readonly';

type Stage =
  | 'loading_config'   // fetching /api/app-config
  | 'ready'            // client ID fetched, waiting for user
  | 'no_client_id'     // server didn't return a client ID
  | 'loading_scripts'  // CDN scripts not yet loaded
  | 'authing'          // Google OAuth popup open
  | 'picking'          // Google Folder Picker open
  | { kind: 'downloading'; done: number; total: number }
  | 'error';

interface Props {
  onFilesReady: (files: File[]) => void;
  onError: (msg: string) => void;
  disabled?: boolean;
}

declare global {
  interface Window {
    gapi: any;
    google: any;
  }
}

// ── Helpers ────────────────────────────────────────────────────

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
    const s = document.createElement('script');
    s.src = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(s);
  });
}

// Singleton so every instance shares the same promise
let scriptsPromise: Promise<void> | null = null;
function ensureScripts(): Promise<void> {
  if (!scriptsPromise) {
    scriptsPromise = Promise.all([
      loadScript('https://apis.google.com/js/api.js'),
      loadScript('https://accounts.google.com/gsi/client'),
    ]).then(() => undefined);
  }
  return scriptsPromise;
}

// ── Component ─────────────────────────────────────────────────

export const GoogleDrivePicker: React.FC<Props> = ({
  onFilesReady,
  onError,
  disabled,
}) => {
  const [stage, setStage] = useState<Stage>('loading_config');
  const [errorMsg, setErrorMsg] = useState('');
  const clientIdRef = useRef('');
  const tokenClientRef = useRef<any>(null);

  // 1. Fetch Google Client ID from the server (set once by the app owner)
  useEffect(() => {
    let cancelled = false;
    fetch('/api/app-config')
      .then(r => r.json())
      .then(data => {
        if (cancelled) return;
        const id: string = data.google_client_id ?? '';
        if (!id) {
          setStage('no_client_id');
          return;
        }
        clientIdRef.current = id;
        // Pre-load CDN scripts in parallel while user reads the UI
        ensureScripts()
          .then(() => { if (!cancelled) setStage('ready'); })
          .catch(() => { if (!cancelled) setStage('loading_scripts'); });
      })
      .catch(() => {
        if (!cancelled) setStage('no_client_id');
      });
    return () => { cancelled = true; };
  }, []);

  // ── Drive helpers ──────────────────────────────────────────

  const downloadFolderImages = useCallback(
    async (folderId: string, token: string): Promise<File[]> => {
      const qs = new URLSearchParams({
        q: `'${folderId}' in parents and mimeType contains 'image/' and trashed=false`,
        fields: 'files(id,name,mimeType)',
        pageSize: '200',
      });
      const listResp = await fetch(
        `https://www.googleapis.com/drive/v3/files?${qs}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!listResp.ok) throw new Error(`Drive API ${listResp.status}: ${listResp.statusText}`);

      const { files = [] } = (await listResp.json()) as {
        files: Array<{ id: string; name: string; mimeType: string }>;
      };
      if (!files.length) throw new Error('No images found in that folder');

      setStage({ kind: 'downloading', done: 0, total: files.length });

      const out: File[] = [];
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        try {
          const resp = await fetch(
            `https://www.googleapis.com/drive/v3/files/${f.id}?alt=media`,
            { headers: { Authorization: `Bearer ${token}` } },
          );
          if (resp.ok) {
            const blob = await resp.blob();
            out.push(new File([blob], f.name, { type: f.mimeType }));
          }
        } catch { /* skip individual failures */ }
        setStage({ kind: 'downloading', done: i + 1, total: files.length });
      }
      return out;
    },
    [],
  );

  const openPicker = useCallback(
    (token: string) => {
      const { gapi, google } = window;
      gapi.load('picker', () => {
        setStage('picking');

        const folderView = new google.picker.DocsView(google.picker.ViewId.FOLDERS)
          .setIncludeFolders(true)
          .setSelectFolderEnabled(true)
          .setMimeTypes('application/vnd.google-apps.folder');

        new google.picker.PickerBuilder()
          .addView(folderView)
          .setTitle('Select a Google Drive folder to import')
          .setOAuthToken(token)
          .setCallback(async (data: any) => {
            if (data.action === google.picker.Action.PICKED) {
              try {
                const files = await downloadFolderImages(data.docs[0].id, token);
                if (files.length > 0) {
                  onFilesReady(files);
                } else {
                  onError('Could not download any images from that folder');
                }
              } catch (err) {
                onError(err instanceof Error ? err.message : 'Google Drive error');
              } finally {
                setStage('ready');
              }
            } else if (data.action === google.picker.Action.CANCEL) {
              setStage('ready');
            }
          })
          .build()
          .setVisible(true);
      });
    },
    [downloadFolderImages, onFilesReady, onError],
  );

  // ── Sign-in handler ────────────────────────────────────────

  const handleSignIn = useCallback(() => {
    const clientId = clientIdRef.current;
    if (!clientId) { onError('Google Sign-In is not configured'); return; }
    if (!window.google?.accounts?.oauth2) {
      // Scripts may not be done loading yet — retry once
      ensureScripts().then(() => {
        if (window.google?.accounts?.oauth2) handleSignIn();
        else onError('Google scripts failed to load — please refresh the page');
      });
      return;
    }

    setStage('authing');

    if (!tokenClientRef.current) {
      tokenClientRef.current = window.google.accounts.oauth2.initTokenClient({
        client_id: clientId,
        scope: SCOPE,
        callback: (resp: any) => {
          if (resp.error) {
            const msg = resp.error === 'access_denied'
              ? 'Access denied — please allow Drive access when prompted'
              : `Sign-in error: ${resp.error_description ?? resp.error}`;
            setErrorMsg(msg);
            onError(msg);
            setStage('ready');
            return;
          }
          openPicker(resp.access_token);
        },
      });
    }

    tokenClientRef.current.requestAccessToken({ prompt: '' });
  }, [onError, openPicker]);

  // ── Render ─────────────────────────────────────────────────

  const downloading = typeof stage === 'object' && stage.kind === 'downloading';

  return (
    <div className="border-2 border-dashed border-frame rounded-xl p-8 bg-white">
      <div className="flex flex-col items-center gap-4 text-center">
        {/* Drive logo */}
        <DriveIcon className="w-10 h-10" />

        {/* ── Loading config ── */}
        {stage === 'loading_config' && (
          <p className="font-jakarta text-sm text-muted-fg">Checking configuration…</p>
        )}

        {/* ── Not configured ── */}
        {(stage === 'no_client_id' || stage === 'loading_scripts') && (
          <div className="space-y-2 max-w-sm">
            <p className="font-jakarta text-sm font-semibold text-foreground">
              Google Drive not configured
            </p>
            <p className="font-jakarta text-xs text-muted-fg leading-relaxed">
              Ask the app administrator to set the{' '}
              <code className="bg-muted px-1 py-0.5 rounded text-foreground">GOOGLE_CLIENT_ID</code>{' '}
              environment variable on Railway to enable Drive import.
            </p>
          </div>
        )}

        {/* ── Ready ── */}
        {stage === 'ready' && (
          <>
            <div className="space-y-1">
              <p className="font-jakarta text-sm font-semibold text-foreground">
                Import photos from Google Drive
              </p>
              <p className="font-jakarta text-xs text-muted-fg">
                Sign in with your Google account, then select a folder
              </p>
            </div>

            <button
              type="button"
              onClick={handleSignIn}
              disabled={disabled}
              className="flex items-center gap-3 px-5 py-2.5 bg-white border-2 border-[#dadce0] rounded-full font-jakarta text-sm font-semibold text-[#3c4043] hover:bg-[#f8f9fa] hover:border-[#d2e3fc] hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}
            >
              <GoogleIcon className="w-4 h-4 flex-shrink-0" />
              Sign in with Google
            </button>

            {errorMsg && (
              <p className="font-jakarta text-xs text-secondary max-w-xs">{errorMsg}</p>
            )}
          </>
        )}

        {/* ── Auth / Picker in progress ── */}
        {(stage === 'authing' || stage === 'picking') && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 justify-center">
              <span className="w-4 h-4 border-2 border-foreground border-t-transparent rounded-full animate-spin" />
              <p className="font-jakarta text-sm font-semibold text-foreground">
                {stage === 'authing' ? 'Waiting for Google sign-in…' : 'Waiting for folder selection…'}
              </p>
            </div>
            <p className="font-jakarta text-xs text-muted-fg">Check for a popup window</p>
          </div>
        )}

        {/* ── Downloading ── */}
        {downloading && typeof stage === 'object' && (
          <div className="w-full max-w-xs space-y-2">
            <p className="font-jakarta text-sm font-semibold text-foreground">
              Downloading photos — {stage.done} / {stage.total}
            </p>
            <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
              <div
                className="bg-accent h-2 rounded-full transition-all duration-200"
                style={{ width: `${Math.round((stage.done / stage.total) * 100)}%` }}
              />
            </div>
            <p className="font-jakarta text-xs text-muted-fg">
              {Math.round((stage.done / stage.total) * 100)}% complete
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Google Drive triangle logo (no external asset) ─────────────
function DriveIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 87.3 78" xmlns="http://www.w3.org/2000/svg" className={className}>
      <path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z" fill="#0066da"/>
      <path d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0-1.2 4.5h27.5z" fill="#00ac47"/>
      <path d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.502l5.852 11.5z" fill="#ea4335"/>
      <path d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z" fill="#00832d"/>
      <path d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z" fill="#2684fc"/>
      <path d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z" fill="#ffba00"/>
    </svg>
  );
}

// ── Google "G" logo for the sign-in button ──────────────────────
function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" className={className}>
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  );
}

export default GoogleDrivePicker;
