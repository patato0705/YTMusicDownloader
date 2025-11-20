// frontend/src/App.tsx
import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import Navbar from "./components/Navbar";
import Home from "./pages/Home";
import Library from "./pages/Library";
import Browse from "./pages/Browse";
import Settings from "./pages/Settings";
import Artist from "./pages/Artist";
import Album from "./pages/Album";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { ChangePassword } from "./pages/ChangePassword";

export default function App(): JSX.Element {
  return (
    <AuthProvider>
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
              <div className="min-h-screen flex flex-col bg-gray-50">
                <Navbar />
                <main className="flex-1 container mx-auto px-4 py-6">
                  <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/library" element={<Library />} />
                    <Route path="/browse" element={<Browse />} />
                    <Route path="/settings" element={<Settings />} />
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
    </AuthProvider>
  );
}