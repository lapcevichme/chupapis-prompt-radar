import type {HTMLAttributes} from 'react';
import {cn} from '@/shared/lib/cn';

interface BadgeProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning';
}

function Badge({className, variant = 'default', ...props}: BadgeProps) {
  const variants = {
    default: 'border-transparent bg-accent text-white shadow-sm',
    secondary: 'border-transparent bg-accent-muted text-accent',
    destructive: 'border-divider bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400',
    outline: 'text-primary border-divider bg-surface',
    success: 'border-divider bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400',
    warning: 'border-divider bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400',
  };

  return (
    <div
      className={cn(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] uppercase tracking-wider font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2',
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

export {Badge};
