import React, { useState, useEffect, useRef } from 'react';
import { fetchSources, fetchSource, uploadFile, triggerRecompute, fetchRecomputeStatus, resumeSource } from '../api';
import type { Source } from '../types';
import { Card, CardContent, CardHeader, CardTitle } from './ui/Card';
import { Badge } from './ui/Badge';
import { UploadCloud, FileText, CheckCircle, Clock, Loader2, RefreshCw, Database, PlayCircle } from 'lucide-react';
import { cn } from '../lib/utils';

interface IngestionProps {
  onFetchSuccess?: () => void;
  refreshTrigger?: number;
}

export default function Ingestion({ onFetchSuccess, refreshTrigger }: IngestionProps) {
  const [sources, setSources] = useState<Source[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [recomputeStatus, setRecomputeStatus] = useState<{ status: string; job_id?: string; scenarios_named?: number }>({ status: 'idle' });
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const [isResuming, setIsResuming] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleResume = async (sourceId: string) => {
    setIsResuming(true);
    try {
      await resumeSource(sourceId);
      const fresh = await fetchSource(sourceId);
      setSelectedSource(fresh);
      loadSources();
    } catch (err) {
      console.error('Resume failed', err);
    } finally {
      setIsResuming(false);
    }
  };

  const loadSources = async () => {
    try {
      const data = await fetchSources();
      setSources(data);
      onFetchSuccess?.();
    } catch (err) {
      console.error('Failed to fetch sources', err);
    }
  };

  const loadRecomputeStatus = async () => {
    try {
      const data = await fetchRecomputeStatus();
      setRecomputeStatus(data);
    } catch (err) {
      console.error('Failed to fetch recompute status', err);
    }
  };

  useEffect(() => {
    loadSources();
    loadRecomputeStatus();
    const interval = setInterval(() => {
      loadSources();
      loadRecomputeStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, [refreshTrigger]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    try {
      await uploadFile(file);
      loadSources();
    } catch (err) {
      console.error('Upload failed', err);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleRecompute = async () => {
    try {
      await triggerRecompute();
      loadRecomputeStatus();
    } catch (err) {
      console.error('Recompute failed', err);
    }
  };

  const handleSourceClick = async (sourceId: string) => {
    try {
      const data = await fetchSource(sourceId);
      setSelectedSource(data);
    } catch (err) {
      console.error('Failed to fetch source details', err);
    }
  };

  const isProcessing = recomputeStatus.status === 'running' || recomputeStatus.status === 'processing';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-secondary">Manage sources and trigger analysis</h2>
        <button
          onClick={handleRecompute}
          disabled={isProcessing}
          className="flex items-center gap-2 px-4 py-2 bg-accent text-white rounded-md text-sm font-semibold hover:bg-accent/90 disabled:opacity-50 transition-colors"
        >
          {isProcessing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          Recompute Scenarios
        </button>
      </div>

      {isProcessing && (
        <Card className="border-accent bg-accent/5">
          <CardContent className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Loader2 className="w-5 h-5 text-accent animate-spin" />
              <div>
                <p className="text-sm font-semibold text-primary">Recomputing Interaction Clusters</p>
                <p className="text-[10px] font-mono text-secondary uppercase tracking-widest mt-1">Analyzing all recent data sources</p>
              </div>
            </div>
            <div className="text-right">
              <span className="text-sm font-medium text-accent">{recomputeStatus.status}</span>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Upload New Source</CardTitle>
            </CardHeader>
            <CardContent>
              <div
                className="border-2 border-dashed border-divider rounded-xl p-8 flex flex-col items-center justify-center bg-surface-hover/50 hover:bg-surface-hover transition-colors cursor-pointer"
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  className="hidden"
                  accept=".csv,.json,.txt"
                />
                {isUploading ? (
                  <div className="flex flex-col items-center">
                    <Loader2 className="w-10 h-10 text-accent animate-spin mb-4" />
                    <p className="text-sm font-medium text-primary">Uploading file...</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center">
                    <UploadCloud className="w-10 h-10 text-secondary mb-4" />
                    <p className="text-sm font-medium text-primary mb-1">Click to upload or drag and drop</p>
                    <p className="text-[10px] font-mono text-secondary uppercase tracking-widest">CSV, JSON or TXT (max. 50MB)</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Data Sources</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-divider">
                {sources.map((source) => (
                  <div 
                    key={source.source_id} 
                    className="flex items-center justify-between p-4 hover:bg-surface-hover transition-colors cursor-pointer"
                    onClick={() => handleSourceClick(source.source_id)}
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-lg bg-surface-hover flex items-center justify-center">
                        <FileText className="w-5 h-5 text-secondary" />
                      </div>
                      <div>
                        <p className="font-semibold text-primary text-sm">{source.name}</p>
                        <p className="text-[10px] font-mono text-secondary uppercase tracking-widest mt-1">
                          {new Date(source.created_at).toLocaleString()} • {source.records_total} records
                        </p>
                      </div>
                    </div>
                    <div>
                      {source.status === 'recomputed' || source.status === 'classified' ? (
                        <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
                          <CheckCircle className="w-3.5 h-3.5" />
                          {source.status}
                        </div>
                      ) : source.status === 'ingesting' ? (
                        <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-amber-600 dark:text-amber-400">
                          <Clock className="w-3.5 h-3.5" />
                          Processing
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-secondary">
                          {source.status}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {sources.length === 0 && (
                  <div className="p-8 text-center text-secondary text-sm">No sources uploaded yet.</div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-1">
          <Card className="h-full min-h-[400px]">
            <CardHeader>
              <CardTitle>Source Details</CardTitle>
            </CardHeader>
            <CardContent>
              {selectedSource ? (
                <div className="space-y-6">
                  <div>
                    <h3 className="text-sm font-semibold text-primary break-words">{selectedSource.name}</h3>
                    <p className="text-[10px] font-mono text-secondary uppercase tracking-widest mt-1">ID: {selectedSource.source_id}</p>
                  </div>
                  
                  <div className="space-y-3 pt-4 border-t border-divider">
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-secondary">Status</span>
                      <Badge variant={selectedSource.status === 'recomputed' || selectedSource.status === 'classified' ? 'success' : 'warning'}>
                        {selectedSource.status}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-secondary">Origin</span>
                      <span className="text-xs font-mono text-primary bg-surface-hover px-2 py-0.5 rounded">{selectedSource.origin}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-secondary">Uploaded</span>
                      <span className="text-xs font-mono text-primary">{new Date(selectedSource.created_at).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}</span>
                    </div>
                  </div>

                  <div className="pt-4 border-t border-divider space-y-4">
                    <div>
                      <div className="flex justify-between items-center mb-1.5">
                        <span className="text-xs font-medium text-primary">Data Health (Ingestion)</span>
                        <span className="text-xs font-mono text-primary">
                          {selectedSource.records_total > 0 
                            ? Math.round((selectedSource.records_valid / selectedSource.records_total) * 100) 
                            : 0}%
                        </span>
                      </div>
                      <div className="w-full h-2 bg-surface-hover rounded-full overflow-hidden flex">
                        <div 
                          className="h-full bg-emerald-500 transition-all duration-500" 
                          style={{ width: `${selectedSource.records_total > 0 ? (selectedSource.records_valid / selectedSource.records_total) * 100 : 0}%` }}
                        />
                        <div 
                          className="h-full bg-red-500 transition-all duration-500" 
                          style={{ width: `${selectedSource.records_total > 0 ? (selectedSource.records_rejected / selectedSource.records_total) * 100 : 0}%` }}
                        />
                      </div>
                    </div>

                    {(() => {
                      // Prefer the authoritative progress (asks ML) over status alone:
                      // "classified" only means streaming finished, not that every
                      // record was indexed.
                      const prog = selectedSource.progress;
                      const classified = prog?.classified ?? selectedSource.records_classified ?? 0;
                      const total = prog?.total ?? selectedSource.records_valid ?? 0;
                      const pct = prog?.percent ?? selectedSource.classification_percentage ?? 0;
                      const done = prog?.done ?? (total > 0 && classified >= total);
                      const stalled = !done && total > 0 && selectedSource.status !== 'ingesting';

                      return (
                        <div>
                          <div className="flex justify-between items-center mb-1.5">
                            <span className="text-xs font-medium text-primary">ML Classification Progress</span>
                            <span className={cn('text-xs font-mono font-bold', done ? 'text-emerald-400' : 'text-accent')}>
                              {classified.toLocaleString()} / {total.toLocaleString()} · {pct}%
                            </span>
                          </div>
                          <div className="w-full h-2 bg-surface-hover rounded-full overflow-hidden flex">
                            <div
                              className={cn('h-full transition-all duration-500', done ? 'bg-emerald-500' : 'bg-accent')}
                              style={{ width: `${Math.min(100, pct)}%` }}
                            />
                          </div>
                          {stalled && (
                            <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-2">
                              <p className="text-xs text-secondary">
                                {(total - classified).toLocaleString()} records are not indexed. This happens when the
                                backend restarts mid-ingest. Resuming re-sends them; already-indexed records are skipped.
                              </p>
                              <button
                                onClick={() => handleResume(selectedSource.source_id)}
                                disabled={isResuming}
                                className="flex items-center gap-2 px-3 py-1.5 bg-accent text-white rounded-md text-xs font-semibold hover:bg-accent/90 disabled:opacity-50 transition-colors"
                              >
                                {isResuming ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PlayCircle className="w-3.5 h-3.5" />}
                                Resume indexing
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-surface-hover rounded-lg p-3 border border-divider">
                        <div className="text-[10px] font-mono text-secondary uppercase tracking-widest mb-1">Valid Records</div>
                        <div className="text-lg font-semibold text-emerald-600 dark:text-emerald-400">{selectedSource.records_valid}</div>
                      </div>
                      <div className="bg-surface-hover rounded-lg p-3 border border-divider">
                        <div className="text-[10px] font-mono text-secondary uppercase tracking-widest mb-1">Classified</div>
                        <div className="text-lg font-semibold text-accent">
                          {selectedSource.status === 'recomputed' || selectedSource.status === 'classified'
                            ? selectedSource.records_valid
                            : (selectedSource.records_classified ?? selectedSource.records_valid)}
                        </div>
                      </div>
                    </div>
                  </div>


                  {selectedSource.normalization_report && (
                    <div className="pt-4 border-t border-divider space-y-3">
                      <span className="text-xs font-medium text-primary">Normalization Report</span>
                      
                      {(selectedSource.normalization_report.synthesized_request_id || selectedSource.normalization_report.synthesized_timestamp) ? (
                        <div className="text-xs text-secondary bg-accent/5 border border-accent/10 rounded-lg p-3 space-y-1.5">
                          <p className="font-medium text-accent">Auto-generated missing fields:</p>
                          {selectedSource.normalization_report.synthesized_request_id ? <p>• {selectedSource.normalization_report.synthesized_request_id} missing Request IDs synthesized</p> : null}
                          {selectedSource.normalization_report.synthesized_timestamp ? <p>• {selectedSource.normalization_report.synthesized_timestamp} missing timestamps synthesized</p> : null}
                        </div>
                      ) : null}

                      {selectedSource.normalization_report.rejected_reasons && Object.keys(selectedSource.normalization_report.rejected_reasons).length > 0 && (
                        <div className="space-y-2">
                          <span className="text-[10px] font-mono text-secondary uppercase tracking-widest">Rejection Reasons</span>
                          <ul className="space-y-1">
                            {Object.entries(selectedSource.normalization_report.rejected_reasons).map(([reason, count]) => (
                              <li key={reason} className="flex justify-between items-center text-xs">
                                <span className="text-secondary">{reason.replace(/_/g, ' ')}</span>
                                <span className="font-mono text-red-500 bg-red-500/10 px-1.5 py-0.5 rounded">{count}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center text-secondary space-y-3 py-12">
                  <Database className="w-8 h-8 opacity-50" />
                  <p className="text-sm">Select a source to view details</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
