// src/components/ui/ExclusionNote.tsx
import React from 'react';
import { Icon } from './icons';

/**
 * Why an artist or album page's Follow / Download button matters more
 * than usual: what's on it was deleted or unfollowed, and nothing
 * automatic brings it back until someone clicks it. Visible text rather
 * than a tooltip, so touch screens read it too.
 */
export const ExclusionNote: React.FC<{ text: string; className?: string }> = ({ text, className = '' }) => (
  <p className={`flex items-start gap-2 text-sm text-muted-foreground ${className}`}>
    <Icon name="info" className="w-4 h-4 mt-0.5 shrink-0" />
    <span>{text}</span>
  </p>
);
