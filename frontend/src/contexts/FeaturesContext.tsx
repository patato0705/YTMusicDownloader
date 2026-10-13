// src/contexts/FeaturesContext.tsx
/**
 * The feature flags, read once for the whole app and re-read after an admin
 * changes settings, so the navbar and the admin panel always agree.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from './AuthContext';
import { getFeatures } from '../api/features';
import type { Features } from '../api/features';

interface FeaturesContextType {
  /** null until loaded (and while signed out) */
  features: Features | null;
  /** Read the flags again, e.g. after the settings were saved */
  refreshFeatures: () => Promise<void>;
}

const FeaturesContext = createContext<FeaturesContextType | undefined>(undefined);

export const FeaturesProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  const [features, setFeatures] = useState<Features | null>(null);

  const refreshFeatures = useCallback(async () => {
    try {
      setFeatures(await getFeatures());
    } catch (err) {
      console.error('Failed to load feature flags:', err);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) refreshFeatures();
    else setFeatures(null);
  }, [isAuthenticated, refreshFeatures]);

  const value = useMemo(() => ({ features, refreshFeatures }), [features, refreshFeatures]);

  return <FeaturesContext.Provider value={value}>{children}</FeaturesContext.Provider>;
};

export const useFeatures = (): FeaturesContextType => {
  const context = useContext(FeaturesContext);
  if (!context) {
    throw new Error('useFeatures must be used within FeaturesProvider');
  }
  return context;
};
