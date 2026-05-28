import { useState, useEffect } from 'react'
import photoTaggerClient from './api/photoTaggerClient'
import { UploadPage } from './pages/UploadPage'
import { SearchPage } from './pages/SearchPage'
import { GalleryPage } from './pages/GalleryPage'
import LoadingSpinner from './components/LoadingSpinner'
import './styles/globals.css'

type Page = 'upload' | 'gallery' | 'search'

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('upload')
  const [isConnected, setIsConnected] = useState<boolean | null>(null)

  useEffect(() => {
    checkConnection()
  }, [])

  const checkConnection = async () => {
    try {
      const response = await photoTaggerClient.healthCheck()
      setIsConnected(response.status === 'ok')
    } catch (error) {
      console.error('Health check failed:', error)
      setIsConnected(false)
    }
  }

  if (isConnected === null) {
    return <LoadingSpinner message="Connecting to PhotoTagger..." />
  }

  if (!isConnected) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Connection Error</h1>
          <p className="text-gray-600 mb-4">
            Could not connect to PhotoTagger backend at http://localhost:5000
          </p>
          <p className="text-sm text-gray-500">
            Make sure the backend is running: <code className="bg-gray-100 px-2 py-1">python -m src.api</code>
          </p>
          <button
            onClick={checkConnection}
            className="mt-6 w-full bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
          >
            Retry Connection
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <h1 className="text-3xl font-bold text-gray-900">PhotoTagger</h1>
          <p className="text-gray-600 mt-1">Tournament Photo Discovery & Analysis</p>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4">
          <div className="flex gap-8">
            <button
              onClick={() => setCurrentPage('upload')}
              className={`px-4 py-4 font-medium transition-colors ${
                currentPage === 'upload'
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Upload
            </button>
            <button
              onClick={() => setCurrentPage('search')}
              className={`px-4 py-4 font-medium transition-colors ${
                currentPage === 'search'
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Search
            </button>
            <button
              onClick={() => setCurrentPage('gallery')}
              className={`px-4 py-4 font-medium transition-colors ${
                currentPage === 'gallery'
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Gallery
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {currentPage === 'upload' && <UploadPage />}
        {currentPage === 'search' && <SearchPage />}
        {currentPage === 'gallery' && <GalleryPage />}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-6xl mx-auto px-4 py-6 text-center text-gray-600 text-sm">
          <p>PhotoTagger © 2026 - Tournament Photo Discovery System</p>
          <p className="mt-1">
            Backend: <span className="font-mono">http://localhost:5000</span>
          </p>
        </div>
      </footer>
    </div>
  )
}

export default App
