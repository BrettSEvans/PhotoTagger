import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import photoTaggerClient from './api/photoTaggerClient'
import { UploadPage } from './pages/UploadPage'
import { GalleryPage } from './pages/GalleryPage'
import { PlayersPage } from './pages/PlayersPage'
import { RosterPage } from './pages/RosterPage'
import LoadingSpinner from './components/LoadingSpinner'
import { NavButton } from './components/NavButton'
import { ErrorBoundary } from './components/ErrorBoundary'
import { SidebarProvider } from './contexts/SidebarContext'
import type { AgentSettings } from './types/index'
import './styles/globals.css'

async function checkConnection(setIsConnected: (value: boolean) => void) {
  try {
    const response = await photoTaggerClient.healthCheck()
    setIsConnected(response.status === 'ok')
  } catch {
    setIsConnected(false)
  }
}

function App() {
  const navigate = useNavigate()
  const [isConnected, setIsConnected] = useState<boolean | null>(null)
  const [agentSettings, setAgentSettings] = useState<AgentSettings>(() => photoTaggerClient.getLocalAgentSettings())

  useEffect(() => {
    checkConnection(setIsConnected)
  }, [])

  const saveLocalAgent = async () => {
    photoTaggerClient.setLocalAgentSettings(agentSettings)
    setIsConnected(null)
    await checkConnection(setIsConnected)
  }

  if (isConnected === null) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center">
        <LoadingSpinner message="Connecting to PhotoTagger…" />
      </div>
    )
  }

  if (!isConnected) {
    return (
      <div className="min-h-screen bg-cream dot-grid flex items-center justify-center p-4">
        <div className="bg-white border-2 border-foreground rounded-2xl shadow-pop-lg p-8 max-w-md w-full relative">
          {/* Decorative corner shape */}
          <div aria-hidden="true" className="absolute -top-4 -right-4 w-10 h-10 bg-secondary rounded-full border-2 border-foreground" />
          <div aria-hidden="true" className="absolute -bottom-3 -left-3 w-7 h-7 bg-tertiary rotate-12 border-2 border-foreground" />

          <div className="w-10 h-10 bg-accent rounded-xl border-2 border-foreground shadow-pop flex items-center justify-center mb-5">
            <svg width="18" height="18" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
              <path d="M12 9v4M12 17h.01" />
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            </svg>
          </div>

          <h1 className="font-outfit text-2xl font-bold text-foreground mb-2">Local agent disconnected</h1>
          <p className="font-jakarta text-muted-fg mb-3">
            Could not connect to the PhotoTagger Local Agent at <span className="font-mono text-foreground text-sm">{agentSettings.localAgentUrl}</span>
          </p>
          <p className="font-jakarta text-sm text-muted-fg mb-6">
            Make sure the local agent is running:<br />
            <code className="bg-muted px-2 py-1 rounded-md text-sm font-mono text-foreground mt-1 inline-block">python -m src.api</code>
          </p>
          <div className="space-y-3 mb-5">
            <label className="block">
              <span className="font-jakarta text-xs font-bold uppercase tracking-wider text-foreground">Local Agent URL</span>
              <input
                value={agentSettings.localAgentUrl}
                onChange={e => setAgentSettings(prev => ({ ...prev, localAgentUrl: e.target.value }))}
                className="geo-input mt-1 w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
              />
            </label>
            <label className="block">
              <span className="font-jakarta text-xs font-bold uppercase tracking-wider text-foreground">Agent Token</span>
              <input
                type="password"
                value={agentSettings.agentToken}
                onChange={e => setAgentSettings(prev => ({ ...prev, agentToken: e.target.value }))}
                className="geo-input mt-1 w-full px-3 py-2 bg-white border-2 border-frame rounded-xl font-jakarta text-sm text-foreground"
              />
            </label>
          </div>
          <button
            onClick={saveLocalAgent}
            className="btn-candy w-full bg-accent text-white font-jakarta font-bold px-6 py-3 rounded-full border-2 border-foreground shadow-pop"
          >
            Save & Retry Connection
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-cream">
      {/* Header */}
      <header className="bg-cream border-b-2 border-foreground relative overflow-hidden">
        <div aria-hidden="true" className="dot-grid absolute inset-0 opacity-40 pointer-events-none" />

        {/* Decorative floating shapes */}
        <div aria-hidden="true" className="absolute top-3 right-16 w-9 h-9 bg-secondary rounded-full border-2 border-foreground opacity-80 animate-float" style={{ animationDelay: '0s' }} />
        <div aria-hidden="true" className="absolute top-5 right-36 w-5 h-5 bg-tertiary rotate-45 border-2 border-foreground opacity-90" />
        <div aria-hidden="true" className="absolute bottom-2 right-24 w-6 h-6 bg-quaternary rounded-full border-2 border-foreground opacity-70 animate-float" style={{ animationDelay: '1.5s' }} />
        <div aria-hidden="true" className="absolute top-2 right-52 w-4 h-4 bg-accent rounded-full border-2 border-foreground opacity-60" />

        <div className="max-w-6xl mx-auto px-4 py-4 relative z-10">
          <div className="flex items-center gap-3">
            {/* Logo mark */}
            <div className="w-9 h-9 bg-accent rounded-xl border-2 border-foreground shadow-pop flex items-center justify-center flex-shrink-0">
              <svg width="18" height="18" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                <rect x="2" y="7" width="20" height="14" rx="2" />
                <path d="M16 7l-2-4H10L8 7" />
                <circle cx="12" cy="14" r="3" />
              </svg>
            </div>
            <div>
              <h1 className="font-outfit text-2xl font-extrabold text-foreground leading-tight">
                PhotoTagger
              </h1>
              <p className="font-jakarta text-xs text-muted-fg font-medium">Tournament Photo Discovery</p>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-cream border-b-2 border-foreground sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4">
          <div className="flex gap-1 overflow-x-auto">
            <NavButton label="1 Roster"   onClick={() => navigate('/roster')} />
            <NavButton label="2 Upload"   onClick={() => navigate('/upload')} />
            <NavButton label="3 Players"  onClick={() => navigate('/players')} />
            <NavButton label="4 Gallery"  onClick={() => navigate('/gallery')} />
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <SidebarProvider>
        <main className="max-w-6xl mx-auto px-4 py-8 flex flex-col">
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Navigate to="/roster" replace />} />
              <Route path="/roster/*" element={<RosterPage />} />
              <Route path="/upload" element={<UploadPage onOpenWorkspace={() => navigate('/players')} onGoToRoster={() => navigate('/roster')} />} />
              <Route path="/players/*" element={<PlayersPage />} />
              <Route path="/player/:clusterId" element={<PlayersPage />} />
              <Route path="/gallery" element={<GalleryPage />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </SidebarProvider>

      {/* Footer */}
      <footer className="border-t-2 border-foreground bg-cream mt-16">
        <div className="max-w-6xl mx-auto px-4 py-5 flex items-center justify-between">
          <p className="font-outfit font-bold text-foreground text-sm">PhotoTagger</p>
          <p className="font-jakarta text-xs text-muted-fg">
            Local Agent: <span className="font-mono">{agentSettings.localAgentUrl}</span>
          </p>
        </div>
      </footer>
    </div>
  )
}

export default App
