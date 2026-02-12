// src/components/ui/ActionCard.tsx
import React from 'react';
import { Link } from 'react-router-dom';

interface ActionCardProps {
  to: string;
  icon: React.ReactNode;
  title: string;
  description: string;
  gradient?: string;
  className?: string;
}

export const ActionCard: React.FC<ActionCardProps> = ({ 
  to, 
  icon, 
  title, 
  description,
  gradient = 'from-blue-500/10 to-indigo-500/10 dark:from-red-900/20 dark:to-red-800/20',
  className = ''
}) => {
  return (
    <Link to={to}>
      <div className={`relative group overflow-hidden rounded-xl glass p-6 border-slate-200 dark:border-white/10 hover:border-blue-400/50 dark:hover:border-red-600/50 transition-all duration-300 hover-lift ${className}`}>
        {/* Background gradient */}
        <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-300`} />
        
        {/* Content */}
        <div className="relative z-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-4 group-hover:scale-110 transition-transform duration-300">
            {icon}
          </div>
          
          <h3 className="text-xl font-bold text-foreground mb-2 group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors">
            {title}
          </h3>
          
          <p className="text-sm text-muted-foreground">
            {description}
          </p>
          
          {/* Arrow indicator */}
          <div className="mt-4 flex items-center gap-2 text-blue-600 dark:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">
            <span className="text-sm font-medium">Get started</span>
            <span className="group-hover:translate-x-1 transition-transform">→</span>
          </div>
        </div>
      </div>
    </Link>
  );
};