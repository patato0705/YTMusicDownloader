// src/components/ui/SectionHeader.tsx
import React from 'react';

interface SectionHeaderProps {
  children: React.ReactNode;
  showDivider?: boolean;
  className?: string;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({ 
  children, 
  showDivider = true,
  className = '' 
}) => {
  return (
    <h2 className={`text-2xl font-bold mb-6 flex items-center gap-3 ${className}`}>
      <span className="text-gradient">{children}</span>
      {showDivider && (
        <div className="h-px flex-1 bg-gradient-to-r from-blue-500/50 dark:from-red-600/50 to-transparent" />
      )}
    </h2>
  );
};