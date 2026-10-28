// src/components/layout/AuthLayout.tsx
import React from 'react';
import { PageBackground } from './PageBackground';
import { Icon } from '../ui/icons';

interface AuthLayoutProps {
  /** Heading above the card; leave out for a page that is just the card */
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
}

/** Full-screen frame of the pages outside the app: sign in, register, change password */
export const AuthLayout: React.FC<AuthLayoutProps> = ({ title, subtitle, children }) => (
  <div className="min-h-screen flex items-center justify-center px-4 py-12 relative overflow-hidden">
    <PageBackground />
    <div className="fixed top-20 left-20 w-96 h-96 bg-accent-500/20 rounded-full blur-3xl pointer-events-none" />
    <div className="fixed bottom-20 right-20 w-96 h-96 bg-accent-500/20 dark:bg-accent-700/20 rounded-full blur-3xl pointer-events-none" />

    <div className="relative max-w-md w-full">
      {/* Which app this is, before what to do in it */}
      <div className="flex items-center justify-center gap-2 mb-8 text-accent-600 dark:text-accent-400">
        <Icon name="music" className="w-7 h-7" />
        <span className="text-xl font-bold">YTMusicDownloader</span>
      </div>
      {title && (
        <div className="text-center mb-8">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground mb-2">{title}</h1>
          {subtitle && <p className="text-muted-foreground text-lg">{subtitle}</p>}
        </div>
      )}
      {children}
    </div>
  </div>
);

/** The glass card holding an auth page's form */
export const AuthCard: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <div className={`glass rounded-3xl p-8 md:p-10 border-gradient shadow-2xl ${className}`}>{children}</div>
);
