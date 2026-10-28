// src/App.tsx
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';

// Layout
import { Navbar } from './components/layout/Navbar';
import { PageBackground } from './components/layout/PageBackground';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ScrollRestoration } from './components/ScrollRestoration';
import { LoadingState } from './components/ui/PageStatus';

// Auth pages
import Login from './pages/auth/Login';
import Register from './pages/auth/Register';
import ChangePassword from './pages/auth/ChangePassword';

// Main pages
import Home from './pages/Home';
import Browse from './pages/Browse';
import Library from './pages/Library';
import Artist from './pages/Artist';
import Album from './pages/Album';
import Charts from './pages/Charts';
import PlaylistImport from './pages/PlaylistImport';
import AdminPanel from './pages/AdminPanel';

export default function App(): JSX.Element {
  const { isLoading } = useAuth();

  // Restoring the session from the refresh cookie
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <PageBackground />
        <LoadingState className="relative" />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <Routes>
        {/* Auth pages: full screen, no navbar */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/change-password"
          element={
            <ProtectedRoute allowTemporaryPassword>
              <ChangePassword />
            </ProtectedRoute>
          }
        />

        {/* The app: signed in, with the navbar */}
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <div className="min-h-screen flex flex-col">
                <PageBackground />
                <Navbar />
                {/* pb clears the phone tab bar (Navbar) and the safe area under it */}
                <main className="relative flex-1 container mx-auto px-4 pt-6 pb-[calc(var(--tab-bar-height)+env(safe-area-inset-bottom)+2.75rem)] md:pb-6">
                  <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/browse" element={<Browse />} />
                    <Route path="/library" element={<Library />} />
                    <Route path="/artists/:artistId" element={<Artist />} />
                    <Route path="/albums/:albumId" element={<Album />} />
                    <Route path="/charts" element={<Charts />} />
                    <Route path="/playlist-import" element={<PlaylistImport />} />
                    <Route
                      path="/admin"
                      element={
                        <ProtectedRoute adminOnly>
                          <AdminPanel />
                        </ProtectedRoute>
                      }
                    />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </main>
              </div>
            </ProtectedRoute>
          }
        />
      </Routes>
      {/* After the routes: runs once the page has mounted (and focused its inputs) */}
      <ScrollRestoration />
    </ErrorBoundary>
  );
}
