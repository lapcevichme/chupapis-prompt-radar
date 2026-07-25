import {useCallback, useEffect, useMemo, useRef, useState, type DragEvent} from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  Hash,
  Loader2,
  type LucideIcon,
  RotateCcw,
  UploadCloud,
} from 'lucide-react';
import type {RecomputeStatus, Source} from '@/entities/source/types';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';
import {formatDateTime} from '@/shared/lib/format';
import {cn} from '@/shared/lib/cn';
import {Badge} from '@/shared/ui/Badge';
import {Card, CardContent, CardHeader, CardTitle} from '@/shared/ui/Card';
import {ErrorState, LoadingState} from '@/widgets/data-state/DataState';

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const ACCEPTED_DATASET_TYPES = '.csv,.json,.jsonl,.txt,application/json,text/csv,text/plain';

interface SourcesPageProps {
  refreshKey: number;
  onWorkspaceChanged: () => void;
}

export default function SourcesPage({refreshKey, onWorkspaceChanged}: SourcesPageProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [localRefreshKey, setLocalRefreshKey] = useState(0);
  const [statusRefreshKey, setStatusRefreshKey] = useState(0);
  const [isDragActive, setIsDragActive] = useState(false);
  const [uploadState, setUploadState] = useState<'idle' | 'uploading'>('idle');
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isRecomputing, setIsRecomputing] = useState(false);

  const sourcesState = useApiResource(() => promptRadarApi.getSources(), [refreshKey, localRefreshKey]);
  const recomputeState = useApiResource(() => promptRadarApi.getRecomputeStatus(), [refreshKey, statusRefreshKey]);
  const selectedSourceState = useApiResource<Source | null>(
    () => (selectedSourceId ? promptRadarApi.getSource(selectedSourceId) : Promise.resolve(null)),
    [selectedSourceId, refreshKey, localRefreshKey],
  );

  const sources = sourcesState.data?.items ?? [];
  const selectedSource = selectedSourceState.data ?? sources.find((source) => source.source_id === selectedSourceId) ?? null;
  const lastUpdated = useMemo(() => {
    const latestCreatedAt = sources
      .map((source) => source.created_at)
      .filter(Boolean)
      .sort()
      .at(-1);
    return latestCreatedAt ? formatDateTime(latestCreatedAt) : 'No source data';
  }, [sources]);

  const refreshSources = useCallback(() => {
    setLocalRefreshKey((key) => key + 1);
    onWorkspaceChanged();
  }, [onWorkspaceChanged]);

  useEffect(() => {
    if (sources.length === 0) {
      setSelectedSourceId(null);
      return;
    }

    if (!selectedSourceId || !sources.some((source) => source.source_id === selectedSourceId)) {
      setSelectedSourceId(sources[0].source_id);
    }
  }, [selectedSourceId, sources]);

  useEffect(() => {
    if (recomputeState.data?.status !== 'running') {
      return;
    }

    const intervalId = window.setInterval(() => {
      setStatusRefreshKey((key) => key + 1);
      setLocalRefreshKey((key) => key + 1);
      onWorkspaceChanged();
    }, 4000);

    return () => window.clearInterval(intervalId);
  }, [onWorkspaceChanged, recomputeState.data?.status]);

  const handleUpload = async (file: File | undefined) => {
    if (!file) {
      return;
    }

    setActionError(null);
    setActionMessage(null);

    if (file.size > MAX_UPLOAD_BYTES) {
      setActionError('File is larger than 50MB');
      return;
    }

    setUploadState('uploading');
    try {
      const source = await promptRadarApi.uploadDataset(file);
      setSelectedSourceId(source.source_id);
      setActionMessage(`${source.name} upload accepted`);
      refreshSources();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Upload failed');
    } finally {
      setUploadState('idle');
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setIsDragActive(false);
    void handleUpload(event.dataTransfer.files.item(0) ?? undefined);
  };

  const handleRecompute = async () => {
    setIsRecomputing(true);
    setActionError(null);
    setActionMessage(null);

    try {
      const job = await promptRadarApi.startRecompute();
      setActionMessage(`Recompute ${job.status}${job.job_id ? ` · ${job.job_id}` : ''}`);
      setStatusRefreshKey((key) => key + 1);
      refreshSources();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Recompute failed');
    } finally {
      setIsRecomputing(false);
    }
  };

  if (sourcesState.isLoading && !sourcesState.data) {
    return <LoadingState title="Loading sources" />;
  }

  if (sourcesState.error) {
    return <ErrorState message={sourcesState.error} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium text-secondary">Manage sources and trigger analysis</p>
          <p className="text-xs text-secondary">Last updated: {lastUpdated}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <RecomputeStatusPill status={recomputeState.data} isLoading={recomputeState.isLoading} />
          <button
            type="button"
            className="inline-flex h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60"
            disabled={isRecomputing}
            onClick={() => void handleRecompute()}
          >
            {isRecomputing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
            Recompute Scenarios
          </button>
        </div>
      </div>

      {(actionMessage || actionError) && (
        <div
          className={cn(
            'rounded-md border px-4 py-3 text-sm',
            actionError
              ? 'border-red-500/30 bg-red-500/10 text-red-400'
              : 'border-blue-500/30 bg-blue-500/10 text-accent',
          )}
        >
          {actionError ?? actionMessage}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Upload New Source</CardTitle>
            </CardHeader>
            <CardContent>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_DATASET_TYPES}
                className="hidden"
                onChange={(event) => void handleUpload(event.target.files?.item(0) ?? undefined)}
              />
              <button
                type="button"
                className={cn(
                  'flex min-h-[180px] w-full flex-col items-center justify-center rounded-md border border-dashed border-divider bg-background/40 px-6 text-center transition-colors hover:border-accent hover:bg-accent-muted/30',
                  isDragActive && 'border-accent bg-accent-muted/40',
                )}
                disabled={uploadState === 'uploading'}
                onClick={() => fileInputRef.current?.click()}
                onDragEnter={(event) => {
                  event.preventDefault();
                  setIsDragActive(true);
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setIsDragActive(false)}
                onDrop={handleDrop}
              >
                {uploadState === 'uploading' ? (
                  <Loader2 className="mb-4 h-10 w-10 animate-spin text-accent" />
                ) : (
                  <UploadCloud className="mb-4 h-10 w-10 text-secondary" />
                )}
                <span className="text-base font-semibold text-primary">
                  {uploadState === 'uploading' ? 'Uploading dataset' : 'Click to upload or drag and drop'}
                </span>
                <span className="mt-2 text-xs uppercase tracking-widest text-secondary">CSV, JSON, JSONL or TXT · max 50MB</span>
              </button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Data Sources</CardTitle>
              <span className="text-sm text-secondary">{sourcesState.data?.total ?? sources.length} total</span>
            </CardHeader>
            <CardContent className="p-0">
              {sources.length === 0 ? (
                <div className="px-6 py-12 text-center">
                  <p className="text-sm font-medium text-primary">No sources yet</p>
                  <p className="mt-2 text-sm text-secondary">Upload a dataset or ingest demo data to start analysis.</p>
                </div>
              ) : (
                <div className="divide-y divide-divider">
                  {sources.map((source) => (
                    <SourceRow
                      key={source.source_id}
                      source={source}
                      isSelected={source.source_id === selectedSourceId}
                      onSelect={() => setSelectedSourceId(source.source_id)}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <SourceDetailsCard source={selectedSource} isLoading={selectedSourceState.isLoading} error={selectedSourceState.error} />
      </div>
    </div>
  );
}

function SourceRow({source, isSelected, onSelect}: {source: Source; isSelected: boolean; onSelect: () => void}) {
  return (
    <button
      type="button"
      className={cn(
        'flex w-full items-center justify-between gap-4 px-6 py-5 text-left transition-colors hover:bg-surface-hover',
        isSelected && 'bg-accent-muted/25',
      )}
      onClick={onSelect}
    >
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-background text-secondary">
          <FileText className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-primary">{source.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-secondary">
            <span>{formatDateTime(source.created_at)}</span>
            <span>{source.origin}</span>
            <span>{source.records_valid.toLocaleString()} / {source.records_total.toLocaleString()} valid</span>
          </div>
        </div>
      </div>
      <SourceStatusBadge status={source.status} />
    </button>
  );
}

function SourceDetailsCard({source, isLoading, error}: {source: Source | null; isLoading: boolean; error: string | null}) {
  return (
    <Card className="min-h-[480px]">
      <CardHeader>
        <CardTitle>Source Details</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="flex min-h-[330px] items-center justify-center gap-3 text-sm font-medium text-secondary">
            <Loader2 className="h-5 w-5 animate-spin text-accent" />
            Loading source
          </div>
        )}
        {!isLoading && error && (
          <div className="rounded-md border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">{error}</div>
        )}
        {!isLoading && !error && !source && (
          <div className="flex min-h-[330px] flex-col items-center justify-center text-center">
            <Database className="mb-4 h-12 w-12 text-secondary/60" />
            <p className="text-sm text-secondary">Select a source to view details</p>
          </div>
        )}
        {!isLoading && !error && source && (
          <div className="space-y-6">
            <div className="space-y-3">
              <SourceStatusBadge status={source.status} />
              <div>
                <h3 className="text-xl font-semibold text-primary">{source.name}</h3>
                <p className="mt-1 break-all text-xs text-secondary">{source.source_id}</p>
              </div>
            </div>

            <CompactDetails
              title="Source Summary"
              items={[
                ['records total', source.records_total.toLocaleString()],
                ['records valid', source.records_valid.toLocaleString()],
                ['records rejected', source.records_rejected.toLocaleString()],
                ['origin', source.origin],
              ]}
            />

            <div className="space-y-3 border-t border-divider pt-5">
              <DetailLine icon={Clock3} label="Created" value={formatDateTime(source.created_at)} />
              <DetailLine icon={Hash} label="Ingested" value={formatOptionalNumber(source.ingested)} />
              <DetailLine icon={CheckCircle2} label="Classified" value={formatOptionalNumber(source.classified)} />
              <DetailLine icon={Database} label="Assigned" value={formatOptionalNumber(source.assigned)} />
            </div>

            <NormalizationReport report={source.normalization_report} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RecomputeStatusPill({status, isLoading}: {status: RecomputeStatus | null; isLoading: boolean}) {
  if (isLoading && !status) {
    return (
      <span className="inline-flex h-10 items-center gap-2 rounded-md border border-divider bg-surface px-3 text-sm text-secondary">
        <Loader2 className="h-4 w-4 animate-spin" />
        Checking status
      </span>
    );
  }

  const normalizedStatus = status?.status ?? 'unknown';
  const isRunning = normalizedStatus === 'running';
  const isFailed = normalizedStatus === 'failed';

  return (
    <span
      className={cn(
        'inline-flex h-10 items-center gap-2 rounded-md border px-3 text-sm font-medium',
        isRunning && 'border-amber-500/30 bg-amber-500/10 text-amber-400',
        isFailed && 'border-red-500/30 bg-red-500/10 text-red-400',
        !isRunning && !isFailed && 'border-blue-500/30 bg-blue-500/10 text-accent',
      )}
    >
      {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
      {normalizedStatus}
      {typeof status?.scenarios_named === 'number' && <span className="text-secondary">· {status.scenarios_named} named</span>}
    </span>
  );
}

function SourceStatusBadge({status}: {status: string}) {
  const normalizedStatus = status.toLowerCase();
  const isFailed = normalizedStatus === 'failed';
  const isProcessing = normalizedStatus === 'ingesting' || normalizedStatus === 'classified';

  if (isFailed) {
    return (
      <Badge variant="destructive" className="gap-1">
        <AlertCircle className="h-3 w-3" />
        Failed
      </Badge>
    );
  }

  if (isProcessing) {
    return (
      <Badge variant="warning" className="gap-1">
        <Clock3 className="h-3 w-3" />
        {status}
      </Badge>
    );
  }

  return (
    <Badge variant="success" className="gap-1">
      <CheckCircle2 className="h-3 w-3" />
      {status}
    </Badge>
  );
}

function DetailLine({icon: Icon, label, value}: {icon: LucideIcon; label: string; value: string}) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="inline-flex items-center gap-2 text-secondary">
        <Icon className="h-4 w-4" />
        {label}
      </span>
      <span className="text-right font-medium text-primary">{value}</span>
    </div>
  );
}

function NormalizationReport({report}: {report: Record<string, unknown> | null | undefined}) {
  if (!report || Object.keys(report).length === 0) {
    return null;
  }

  return (
    <div className="border-t border-divider pt-5">
      <CompactDetails
        title="Normalization Report"
        items={Object.entries(report)
          .slice(0, 6)
          .map(([key, value]) => [key.replaceAll('_', ' '), formatReportValue(value)])}
      />
    </div>
  );
}

function CompactDetails({title, items}: {title: string; items: Array<[string, string]>}) {
  return (
    <section className="space-y-3">
      <h4 className="text-sm font-semibold text-primary">{title}</h4>
      <div className="space-y-2.5">
        {items.map(([label, value]) => (
          <div key={label} className="flex items-start justify-between gap-4 text-sm">
            <span className="text-secondary">{label}</span>
            <span className="max-w-[190px] truncate text-right font-semibold text-primary">{value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatOptionalNumber(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : 'No data';
}

function formatReportValue(value: unknown) {
  if (value === null || value === undefined) {
    return 'No data';
  }

  if (typeof value === 'object') {
    return JSON.stringify(value);
  }

  return String(value);
}
