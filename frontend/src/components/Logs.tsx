import React, { useState, useEffect } from 'react';
import { fetchLogs } from '../api';
import type { LogItem, DashboardFilters } from '../types';
import { Card, CardContent } from './ui/Card';
import { Badge } from './ui/Badge';
import { Loader2, ChevronDown } from 'lucide-react';
import { cn } from '../lib/utils';

interface LogsProps {
  filters?: DashboardFilters;
  onFetchSuccess?: () => void;
  refreshTrigger?: number;
}

const PAGE_SIZE = 100;

export default function Logs({ onFetchSuccess, refreshTrigger, filters }: LogsProps) {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  // Polling refreshes the pages already on screen rather than snapping back to
  // the first one, so "load more" survives the 5s refresh.
  const loadData = async (silent = false, size = PAGE_SIZE) => {
    try {
      if (!silent && logs.length === 0) setLoading(true);
      const page = await fetchLogs(filters, size);
      setLogs(page.items);
      setTotal(page.total);
      onFetchSuccess?.();
    } catch (err) {
      console.error('Failed to load logs', err);
    } finally {
      setLoading(false);
    }
  };

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const page = await fetchLogs(filters, PAGE_SIZE, logs.length);
      setLogs((prev) => [...prev, ...page.items]);
      setTotal(page.total);
    } catch (err) {
      console.error('Failed to load more logs', err);
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    setLogs([]);
    loadData(false);
  }, [filters]);

  useEffect(() => {
    loadData(false, Math.max(PAGE_SIZE, logs.length));
    const interval = setInterval(() => {
      loadData(true, Math.max(PAGE_SIZE, logs.length));
    }, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTrigger]);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="flex justify-center p-12">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-secondary">
          Raw prompt data and classification
          {total > 0 && (
            <span className="ml-2 text-secondary/70">
              — показано {logs.length.toLocaleString('ru-RU')} из {total.toLocaleString('ru-RU')}
            </span>
          )}
        </h2>
      </div>

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
                {logs.map((log) => (
                  <tr key={log.request_id} className="hover:bg-surface-hover transition-colors">
                    <td className="px-6 py-4 text-secondary whitespace-nowrap">
                      {formatDate(log.timestamp)}
                    </td>
                    <td className="px-6 py-4 font-medium text-primary max-w-md truncate">
                      {log.query_text}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1">
                        <span className={cn('font-medium', log.task_type ? 'text-primary' : 'text-secondary italic')}>
                          {log.scenario_name || log.label || log.task_type || 'Not classified yet'}
                        </span>
                        <span className="text-xs text-secondary">
                          {log.classification_confidence != null
                            ? `${Math.round(log.classification_confidence * 100)}% confidence`
                            : 'awaiting classification'}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {log.has_failure_signals ? (
                        <div className="flex items-center gap-2 text-sm font-medium text-red-600 dark:text-red-400">
                           <div className="w-1.5 h-1.5 rounded-full bg-red-600 dark:bg-red-400" />
                           Failed
                        </div>
                      ) : log.is_outlier ? (
                        <div className="flex items-center gap-2 text-sm font-medium text-amber-600 dark:text-amber-400">
                           <div className="w-1.5 h-1.5 rounded-full bg-amber-600 dark:bg-amber-400" />
                           Outlier
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 text-sm font-medium text-accent">
                           <div className="w-1.5 h-1.5 rounded-full bg-accent" />
                           Success
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {logs.length < total && (
            <div className="p-4 border-t border-divider flex justify-center">
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-secondary hover:text-primary hover:bg-surface-hover disabled:opacity-60 rounded-md transition-colors"
              >
                {loadingMore ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ChevronDown className="w-4 h-4" />
                )}
                Показать ещё {Math.min(PAGE_SIZE, total - logs.length)}
              </button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
