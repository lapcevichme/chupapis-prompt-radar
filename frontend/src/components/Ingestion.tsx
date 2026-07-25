import React, { useState, useEffect, useRef } from 'react';
import { fetchSources, fetchSource, uploadFile, triggerRecompute, fetchRecomputeStatus } from '../api';
import type { Source } from '../types';
import { Card, CardContent, CardHeader, CardTitle } from './ui/Card';
import { Badge } from './ui/Badge';
import { UploadCloud, FileText, CheckCircle, Clock, Loader2, RefreshCw, Database } from 'lucide-react';

export default function Ingestion() {
  const [sources, setSources] = useState<Source[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [recomputeStatus, setRecomputeStatus] = useState<{ status: string; job_id?: string; scenarios_named?: number }>({ status: 'idle' });
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSources = async () => {
    try {
      const data = await fetchSources();
      setSources(data);
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
  }, []);

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
                      <Badge variant={selectedSource.status === 'recomputed' ? 'success' : 'warning'}>
                        {selectedSource.status}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-secondary">Records</span>
                      <span className="text-xs font-mono text-primary">{selectedSource.records_total} total / {selectedSource.records_valid} valid</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-secondary">Origin</span>
                      <span className="text-xs font-mono text-primary">{selectedSource.origin}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-secondary">Uploaded</span>
                      <span className="text-xs font-mono text-primary">{new Date(selectedSource.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
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
