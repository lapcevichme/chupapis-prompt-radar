import React, { useState, useEffect } from 'react';
import { fetchLogs } from '../api';
import type { LogItem } from '../types';
import { Card, CardContent } from './ui/Card';
import { Badge } from './ui/Badge';
import { Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';

interface LogsProps {
  onFetchSuccess?: () => void;
  refreshTrigger?: number;
}

export default function Logs({ onFetchSuccess, refreshTrigger }: LogsProps) {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = async (silent = false) => {
    try {
      if (!silent && logs.length === 0) setLoading(true);
      const data = await fetchLogs();
      setLogs(data);
      onFetchSuccess?.();
    } catch (err) {
      console.error('Failed to load logs', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(false);
    const interval = setInterval(() => {
      loadData(true);
    }, 5000);
    return () => clearInterval(interval);
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
        <h2 className="text-sm font-medium text-secondary">Raw prompt data and classification</h2>
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
        </CardContent>
      </Card>
    </div>
  );
}
