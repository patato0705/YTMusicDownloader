// src/components/ProtectedRoute.tsx
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
  /** Administrators only; anyone else is sent home */
  adminOnly?: boolean;
  /** The page choosing a new password, the only one open with a temporary password */
  allowTemporaryPassword?: boolean;
}

/** Signed-in users only (App waits for the session check before rendering routes) */
export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, adminOnly = false, allowTemporaryPassword = false }) => {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Temporary password (first admin, or reset by an admin): choose one first
  if (user.must_change_password && !allowTemporaryPassword) {
    return <Navigate to="/change-password" replace />;
  }

  if (adminOnly && user.role !== 'administrator') {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
};
