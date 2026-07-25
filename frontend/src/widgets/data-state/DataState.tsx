import {AlertTriangle, Loader2} from 'lucide-react';
import {Card, CardContent} from '@/shared/ui/Card';

interface LoadingStateProps {
  title?: string;
}

export function LoadingState({title = 'Loading data'}: LoadingStateProps) {
  return (
    <Card className="w-full">
      <CardContent className="p-8 flex items-center justify-center gap-3 text-secondary">
        <Loader2 className="w-5 h-5 animate-spin text-accent" />
        <span className="text-sm font-medium">{title}</span>
      </CardContent>
    </Card>
  );
}

interface ErrorStateProps {
  title?: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function ErrorState({title = 'Request failed', message, actionLabel, onAction}: ErrorStateProps) {
  return (
    <Card className="w-full max-w-xl">
      <CardContent className="p-8">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-500 mt-0.5" />
          <div className="min-w-0">
            <h2 className="font-semibold text-primary">{title}</h2>
            <p className="text-sm text-secondary mt-2 break-words">{message}</p>
            {actionLabel && onAction && (
              <button
                className="mt-5 inline-flex items-center rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90"
                onClick={onAction}
              >
                {actionLabel}
              </button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function EmptyState({title}: {title: string}) {
  return (
    <Card>
      <CardContent className="p-8 text-center text-sm text-secondary">{title}</CardContent>
    </Card>
  );
}
