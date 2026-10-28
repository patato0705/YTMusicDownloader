// src/components/ui/Pill.tsx
import React from 'react';

interface PillProps {
  /** Background, text and border colours */
  tone: string;
  /** SVG path of the icon */
  icon: string;
  strokeWidth?: number;
  label: string;
  /** Hover text */
  title?: string;
  /** Classes of the label, e.g. to hide it on phones */
  labelClassName?: string;
  /** Renders as a button when set */
  onClick?: () => void;
  className?: string;
}

/** Small rounded badge with an icon: the track status and lyrics columns */
export const Pill: React.FC<PillProps> = ({ tone, icon, strokeWidth = 2, label, title, labelClassName = '', onClick, className = '' }) => {
  const classes = `inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium whitespace-nowrap rounded-full border backdrop-blur-sm ${tone} ${className}`;
  const content = (
    <>
      <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth} d={icon} />
      </svg>
      <span className={labelClassName}>{label}</span>
    </>
  );

  return onClick ? (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`${classes} hover:ring-2 hover:ring-accent-500/40 focus:outline-none focus:ring-2 focus:ring-accent-500 dark:focus:ring-accent-600 transition-shadow`}
    >
      {content}
    </button>
  ) : (
    <span className={classes} title={title}>{content}</span>
  );
};
