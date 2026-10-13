// src/components/layout/AuthLayout.tsx
import React from 'react';
import { PageBackground } from './PageBackground';

interface AuthLayoutProps {
  /** Heading above the card; leave out for a page that is just the card */
  title?: string;
  /** The emoji between the two lines under the title */
  emoji?: string;
  subtitle?: string;
  children: React.ReactNode;
}

/** Full-screen frame of the pages outside the app: sign in, register, change password */
export const AuthLayout: React.FC<AuthLayoutProps> = ({ title, emoji, subtitle, children }) => (
  <div className="min-h-screen flex items-center justify-center px-4 py-12 relative overflow-hidden">
    <PageBackground />
    <div className="fixed top-20 left-20 w-96 h-96 bg-blue-500/20 dark:bg-red-500/20 rounded-full blur-3xl pointer-events-none" />
    <div className="fixed bottom-20 right-20 w-96 h-96 bg-indigo-500/20 dark:bg-red-700/20 rounded-full blur-3xl pointer-events-none" />

    <div className="relative max-w-md w-full">
      {title && (
        <div className="text-center mb-8">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">
            <span className="text-gradient">{title}</span>
          </h1>
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent to-blue-500 dark:to-red-500" />
            <span className="text-xl" aria-hidden="true">{emoji}</span>
            <div className="h-px flex-1 bg-gradient-to-l from-transparent to-blue-500 dark:to-red-500" />
          </div>
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
