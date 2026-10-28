// src/components/ui/ActionCard.tsx
import React from 'react';
import { Link } from 'react-router-dom';
import { Icon } from './icons';
import type { IconName } from './icons';

interface ActionCardProps {
  to: string;
  icon: IconName;
  title: string;
  description: string;
  className?: string;
}

/** A "get started" link card: where to go next, with a line saying what's there */
export const ActionCard: React.FC<ActionCardProps> = ({ to, icon, title, description, className = '' }) => (
  <Link
    to={to}
    className={`group flex items-center gap-4 h-full rounded-xl glass p-4 sm:p-5 border-slate-200 dark:border-white/10 hover:border-accent-400/60 dark:hover:border-accent-500/50 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent-500/70 ${className}`}
  >
    <div className="flex shrink-0 items-center justify-center w-12 h-12 rounded-xl bg-accent-500/10 text-accent-600 dark:text-accent-400 transition-colors group-hover:bg-accent-600 group-hover:text-white dark:group-hover:bg-accent-500">
      <Icon name={icon} className="w-6 h-6" />
    </div>
    <div className="min-w-0">
      <h3 className="font-semibold text-foreground group-hover:text-accent-600 dark:group-hover:text-accent-400 transition-colors">
        {title}
      </h3>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  </Link>
);
