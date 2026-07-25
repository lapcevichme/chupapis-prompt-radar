import {useState} from 'react';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';
import {formatDateTime, titleFromCode} from '@/shared/lib/format';
import {Card, CardContent} from '@/shared/ui/Card';
import {Pagination} from '@/shared/ui/Pagination';
import {EmptyState, ErrorState, LoadingState} from '@/widgets/data-state/DataState';

const PAGE_SIZE = 7;

interface LogsPageProps {
  refreshKey: number;
}

export default function LogsPage({refreshKey}: LogsPageProps) {
  const [offset, setOffset] = useState(0);
  const [onlyFailures, setOnlyFailures] = useState(false);
  const {data, error, isLoading} = useApiResource(
    () => promptRadarApi.getLogs({limit: PAGE_SIZE, offset, only_failures: onlyFailures}),
    [refreshKey, offset, onlyFailures],
  );

  if (isLoading) {
    return <LoadingState title="Loading logs" />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!data) {
    return <EmptyState title="No logs found" />;
  }

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const currentPage = Math.min(Math.floor(offset / PAGE_SIZE), totalPages - 1);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <h2 className="text-sm font-medium text-secondary">Raw prompt data and classification · {data.total} records</h2>
        <label className="flex items-center gap-2 text-sm font-medium text-primary">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--color-accent)]"
            checked={onlyFailures}
            onChange={(event) => {
              setOffset(0);
              setOnlyFailures(event.target.checked);
            }}
          />
          Failures only
        </label>
      </div>

      {data.items.length === 0 ? (
        <EmptyState title="No logs match current filters" />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-secondary bg-surface-hover border-b border-divider">
                  <tr>
                    <th className="px-6 py-4 font-medium">Timestamp</th>
                    <th className="px-6 py-4 font-medium">Query</th>
                    <th className="px-6 py-4 font-medium">Classification</th>
                    <th className="px-6 py-4 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-divider">
                  {data.items.map((log) => (
                    <tr key={log.request_id} className="hover:bg-surface-hover transition-colors">
                      <td className="px-6 py-4 text-secondary whitespace-nowrap">{formatDateTime(log.timestamp)}</td>
                      <td className="px-6 py-4 font-medium text-primary max-w-md truncate">{log.query_text}</td>
                      <td className="px-6 py-4">
                        <div className="flex flex-col gap-1">
                          <span className="font-medium text-primary">{log.scenario_name || log.label || titleFromCode(log.task_type)}</span>
                          <span className="text-xs text-secondary">{Math.round((log.classification_confidence ?? 0) * 100)}% confidence</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <LogStatus hasFailureSignals={log.has_failure_signals} isOutlier={log.is_outlier} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={(page) => setOffset(page * PAGE_SIZE)}
        ariaLabel="Logs pagination"
      />
    </div>
  );
}

function LogStatus({hasFailureSignals, isOutlier}: {hasFailureSignals: boolean; isOutlier: boolean}) {
  if (hasFailureSignals) {
    return (
      <div className="flex items-center gap-2 text-sm font-medium text-red-600 dark:text-red-400">
        <div className="w-1.5 h-1.5 rounded-full bg-red-600 dark:bg-red-400" />
        Failed
      </div>
    );
  }

  if (isOutlier) {
    return (
      <div className="flex items-center gap-2 text-sm font-medium text-amber-600 dark:text-amber-400">
        <div className="w-1.5 h-1.5 rounded-full bg-amber-600 dark:bg-amber-400" />
        Outlier
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-sm font-medium text-accent">
      <div className="w-1.5 h-1.5 rounded-full bg-accent" />
      Success
    </div>
  );
}
