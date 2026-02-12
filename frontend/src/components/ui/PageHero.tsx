// src/components/ui/PageHero.tsx
import React from 'react';

interface PageHeroProps {
  badge?: {
    text: string;
    online?: boolean;
  };
  title: React.ReactNode;
  subtitle?: string;
  children?: React.ReactNode;
  className?: string;
}

export const PageHero: React.FC<PageHeroProps> = ({ 
  badge,
  title, 
  subtitle,
  children,
  className = '' 
}) => {
  return (
    <div className={`relative overflow-hidden rounded-2xl bg-gradient-tech border border-slate-200 dark:border-white/10 p-8 md:p-12 ${className}`}>
      {/* Animated background elements */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-blue-500/10 dark:bg-red-900/15 rounded-full blur-3xl animate-pulse" />
      <div className="absolute bottom-0 left-0 w-96 h-96 bg-indigo-500/8 dark:bg-red-800/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      
      <div className="relative z-10">
        {badge && (
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass mb-6">
            {badge.online && (
              <div className="w-2 h-2 bg-blue-600 dark:bg-red-600 rounded-full animate-pulse" />
            )}
            <span className="text-sm text-blue-600 dark:text-red-400 font-medium">{badge.text}</span>
          </div>
        )}
        
        <h1 className="text-4xl md:text-6xl font-bold mb-4">
          {title}
        </h1>
        
        {subtitle && (
          <p className="text-xl text-muted-foreground max-w-2xl">
            {subtitle}
          </p>
        )}

        {children && (
          <div className="mt-6">
            {children}
          </div>
        )}
      </div>
    </div>
  );
};