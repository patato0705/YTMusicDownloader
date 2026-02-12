// src/components/ui/Card.tsx
import React from 'react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  variant?: 'default' | 'glass';
}

export const Card: React.FC<CardProps> = ({ 
  children, 
  variant = 'glass',
  className = '', 
  ...props 
}) => {
  const variants = {
    default: 'bg-white dark:bg-card border border-slate-200 dark:border-border shadow-sm',
    glass: 'glass', // Uses the glass utility class from index.css
  };

  return (
    <div
      className={`text-card-foreground rounded-xl ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader: React.FC<CardProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`p-6 ${className}`} {...props}>
      {children}
    </div>
  );
};

export const CardTitle: React.FC<CardProps> = ({ children, className = '', ...props }) => {
  return (
    <h3 className={`text-2xl font-semibold leading-none tracking-tight text-foreground ${className}`} {...props}>
      {children}
    </h3>
  );
};

export const CardDescription: React.FC<CardProps> = ({ children, className = '', ...props }) => {
  return (
    <p className={`text-sm text-muted-foreground mt-1.5 ${className}`} {...props}>
      {children}
    </p>
  );
};

export const CardContent: React.FC<CardProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`p-6 pt-0 ${className}`} {...props}>
      {children}
    </div>
  );
};

export const CardFooter: React.FC<CardProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`flex items-center p-6 pt-0 ${className}`} {...props}>
      {children}
    </div>
  );
};