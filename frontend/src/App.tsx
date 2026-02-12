// src/App.tsx
import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';

// Layout
import Navbar from './components/layout/Navbar';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ErrorBoundary } from './components/ErrorBoundary';

// Auth pages
import { Login } from './pages/auth/Login';
import { Register } from './pages/auth/Register';
import { ChangePassword } from './pages/auth/ChangePassword';

// Main pages
import Home from './pages/Home';
import Browse from './pages/Browse';
import Library from './pages/Library';
//import Settings from './pages/Settings';
import Artist from './pages/Artist';
import Album from './pages/Album';

export default function App(): JSX.Element {
  const { isLoading } = useAuth();

  // Show loading spinner while checking auth
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <Routes>
        {/* Public auth routes - full screen, no navbar */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/change-password" element={<ChangePassword />} />

        {/* Protected routes - with navbar */}
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <div className="min-h-screen flex flex-col bg-background">
                <Navbar />
                <main className="flex-1 container mx-auto px-4 py-6">
                  <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/browse" element={<Browse />} />
                    <Route path="/library" element={<Library />} />
                    {/* <Route path="/settings" element={<Settings />} /> */}
                    <Route path="/artists/:artistId" element={<Artist />} />
                    <Route path="/albums/:albumId" element={<Album />} />
                    
                    {/* Catch-all redirect */}
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </main>
              </div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </ErrorBoundary>
  );
}