import {ChevronLeft, ChevronRight} from 'lucide-react';
import {cn} from '@/shared/lib/cn';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  ariaLabel: string;
  className?: string;
}

export function Pagination({currentPage, totalPages, onPageChange, ariaLabel, className}: PaginationProps) {
  if (totalPages <= 1) {
    return null;
  }

  const pageItems = getPaginationItems(currentPage, totalPages);

  return (
    <nav
      className={cn(
        'mt-auto flex min-h-12 w-full max-w-[380px] items-center justify-between gap-1 self-start rounded-md border border-divider bg-background/60 px-2 py-1.5 md:w-1/2 md:min-w-[320px]',
        className,
      )}
      aria-label={ariaLabel}
    >
      <button
        aria-label="Previous page"
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-accent transition-colors hover:bg-accent-muted disabled:cursor-default disabled:text-secondary disabled:opacity-30"
        disabled={currentPage === 0}
        onClick={() => onPageChange(Math.max(0, currentPage - 1))}
      >
        <ChevronLeft className="h-5 w-5" />
      </button>

      <div className="flex min-w-0 flex-1 items-center justify-center gap-0.5 sm:gap-1.5">
        {pageItems.map((item, index) =>
          item === 'ellipsis' ? (
            <span key={`ellipsis-${index}`} className="flex h-9 min-w-7 items-center justify-center text-sm font-semibold text-accent">
              ...
            </span>
          ) : (
            <button
              key={item}
              aria-current={item === currentPage ? 'page' : undefined}
              className={
                item === currentPage
                  ? 'inline-flex h-9 min-w-9 items-center justify-center rounded-md bg-accent px-2.5 text-sm font-semibold text-white shadow-sm'
                  : 'inline-flex h-9 min-w-9 items-center justify-center rounded-md px-2.5 text-sm font-semibold text-accent transition-colors hover:bg-accent-muted'
              }
              onClick={() => onPageChange(item)}
            >
              {item + 1}
            </button>
          ),
        )}
      </div>

      <button
        aria-label="Next page"
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-accent transition-colors hover:bg-accent-muted disabled:cursor-default disabled:text-secondary disabled:opacity-30"
        disabled={currentPage >= totalPages - 1}
        onClick={() => onPageChange(Math.min(totalPages - 1, currentPage + 1))}
      >
        <ChevronRight className="h-5 w-5" />
      </button>
    </nav>
  );
}

function getPaginationItems(currentPage: number, totalPages: number): Array<number | 'ellipsis'> {
  if (totalPages <= 7) {
    return Array.from({length: totalPages}, (_, index) => index);
  }

  const lastPage = totalPages - 1;

  if (currentPage <= 3) {
    return [0, 1, 2, 3, 4, 'ellipsis', lastPage];
  }

  if (currentPage >= lastPage - 3) {
    return [0, 'ellipsis', lastPage - 4, lastPage - 3, lastPage - 2, lastPage - 1, lastPage];
  }

  return [0, 'ellipsis', currentPage - 1, currentPage, currentPage + 1, 'ellipsis', lastPage];
}
