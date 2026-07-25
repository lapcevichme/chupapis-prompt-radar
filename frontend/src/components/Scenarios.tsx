import React, { useState, useEffect } from 'react';
import { fetchScenarios, fetchScenarioDetail } from '../api';
import type { Scenario } from '../types';
import { Card, CardContent, CardHeader, CardTitle } from './ui/Card';
import { Badge } from './ui/Badge';
import { TrendingUp, TrendingDown, Minus, Target, Bot, ArrowLeft, Clock, Loader2 } from 'lucide-react';

interface ScenariosProps {
  onFetchSuccess?: () => void;
  refreshTrigger?: number;
}

export default function Scenarios({ onFetchSuccess, refreshTrigger }: ScenariosProps) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [scenarioDetails, setScenarioDetails] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadData = async (silent = false) => {
    try {
      if (!silent && scenarios.length === 0) setLoading(true);
      const data = await fetchScenarios();
      setScenarios(data);
      onFetchSuccess?.();
    } catch (err) {
      console.error('Failed to load scenarios', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(false);
    const interval = setInterval(() => {
      loadData(true);
    }, 10000);
    return () => clearInterval(interval);
  }, [refreshTrigger]);

  const handleScenarioClick = async (id: string) => {
    setSelectedScenarioId(id);
    setDetailLoading(true);
    try {
      const data = await fetchScenarioDetail(id);
      setScenarioDetails(data);
    } catch (err) {
      console.error(err);
      setScenarioDetails(scenarios.find(s => s.scenario_id === id));
    } finally {
      setDetailLoading(false);
    }
  };

  // Before recompute, ML holds one raw online cluster per record: unnamed,
  // unsummarized, count=1. Those are pipeline internals, not scenarios — hide
  // them and tell the user what to do instead of rendering blank cards.
  const namedScenarios = scenarios.filter((s) => s.name && s.name.trim().length > 0);
  const rawClusterCount = scenarios.length - namedScenarios.length;

  if (loading) {
    return (
      <div className="flex justify-center p-12">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  if (selectedScenarioId) {
    return (
      <div className="space-y-6">
        <button 
          onClick={() => { setSelectedScenarioId(null); setScenarioDetails(null); }}
          className="flex items-center gap-2 text-sm font-medium text-secondary hover:text-primary transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Scenarios
        </button>

        {detailLoading ? (
          <div className="flex justify-center p-12">
            <div className="animate-spin w-8 h-8 border-4 border-accent border-t-transparent rounded-full" />
          </div>
        ) : scenarioDetails ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between mb-4">
                    <Badge variant="secondary">{scenarioDetails.task_type?.replace('_', ' ')}</Badge>
                    {scenarioDetails.automation_potential === 'high' && <Badge variant="success">High ROI</Badge>}
                  </div>
                  <CardTitle className="text-2xl">{scenarioDetails.name}</CardTitle>
                  <p className="text-secondary mt-2">{scenarioDetails.summary}</p>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <h4 className="text-sm font-semibold text-primary uppercase tracking-wider mb-2">User Goal</h4>
                    <p className="text-sm text-secondary bg-surface-hover p-4 rounded-lg border border-divider">
                      {scenarioDetails.user_goal}
                    </p>
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-primary uppercase tracking-wider mb-2">Pain Points</h4>
                    <ul className="space-y-2">
                      {scenarioDetails.pain_points?.map((pt: string, i: number) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-secondary">
                          <Minus className="w-4 h-4 text-accent mt-0.5" />
                          {pt}
                        </li>
                      ))}
                    </ul>
                  </div>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader>
                  <CardTitle>Representative Examples</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="divide-y divide-divider">
                    {scenarioDetails.representative_examples?.map((ex: string, i: number) => (
                      <div key={i} className="py-4 first:pt-0 last:pb-0">
                        <p className="text-sm text-primary font-medium">{ex}</p>
                      </div>
                    ))}
                    {!scenarioDetails.representative_examples?.length && (
                      <p className="text-sm text-secondary">No examples available.</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
            
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Metrics</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <p className="text-xs text-secondary uppercase tracking-wider">Volume</p>
                    <div className="flex items-end gap-2 mt-1">
                      <span className="text-3xl font-semibold text-primary">{scenarioDetails.count}</span>
                      <span className="text-sm text-secondary mb-1">requests</span>
                    </div>
                  </div>
                  
                  <div>
                    <p className="text-xs text-secondary uppercase tracking-wider">Growth</p>
                    <div className="flex items-center gap-2 mt-1">
                      {scenarioDetails.trend === 'up' ? (
                        <TrendingUp className="w-5 h-5 text-accent" />
                      ) : scenarioDetails.trend === 'down' ? (
                        <TrendingDown className="w-5 h-5 text-red-500" />
                      ) : (
                        <Minus className="w-5 h-5 text-secondary" />
                      )}
                      <span className={`text-2xl font-semibold ${scenarioDetails.trend === 'up' ? 'text-accent' : scenarioDetails.trend === 'down' ? 'text-red-500' : 'text-primary'}`}>
                        {scenarioDetails.growth_rate_percent}%
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-secondary">Auto-discovered user interaction clusters</h2>
      </div>

      {namedScenarios.length === 0 && (
        <Card>
          <CardContent className="py-16 flex flex-col items-center text-center gap-3">
            <Target className="w-10 h-10 text-secondary opacity-40" />
            <p className="text-sm font-semibold text-primary">Scenarios not built yet</p>
            <p className="text-sm text-secondary max-w-md">
              {rawClusterCount > 0
                ? `${rawClusterCount.toLocaleString()} records are classified and waiting to be grouped. Run "Recompute Scenarios" on the Ingestion & Sources page to cluster them and generate names and summaries.`
                : 'Upload a dataset on the Ingestion & Sources page, then run "Recompute Scenarios" to discover interaction clusters.'}
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {namedScenarios.map((scenario) => (
          <Card 
            key={scenario.scenario_id} 
            className="flex flex-col hover:border-accent/50 transition-colors cursor-pointer group"
            onClick={() => handleScenarioClick(scenario.scenario_id)}
          >
            <CardHeader className="pb-4">
              <div className="flex justify-between items-start mb-3">
                <Badge variant="secondary">
                  {scenario.task_type?.replace('_', ' ')}
                </Badge>
                {scenario.automation_potential === 'high' && (
                  <Badge variant="success" className="flex items-center gap-1">
                    <Bot className="w-3 h-3" />
                    High ROI
                  </Badge>
                )}
              </div>
              <CardTitle className="text-primary group-hover:text-accent transition-colors">{scenario.name}</CardTitle>
              <p className="text-sm text-secondary line-clamp-2 mt-2 leading-relaxed">{scenario.summary}</p>
            </CardHeader>
            <CardContent className="flex-1">
              <div className="space-y-5">
                <div>
                  <div className="text-xs font-semibold text-secondary uppercase tracking-wider mb-2 flex items-center gap-1">
                    <Target className="w-3.5 h-3.5" /> User Goal
                  </div>
                  <p className="text-sm text-primary">{scenario.user_goal}</p>
                </div>
                <div>
                  <div className="text-xs font-semibold text-secondary uppercase tracking-wider mb-2">Pain Points</div>
                  <ul className="text-sm text-primary list-disc list-inside space-y-1">
                    {scenario.pain_points?.map((pt, i) => (
                      <li key={i}>{pt}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </CardContent>
            <div className="p-4 border-t border-divider bg-surface-hover flex justify-between items-center text-sm rounded-b-xl">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-primary text-lg">{scenario.count}</span>
                <span className="text-secondary">requests</span>
              </div>
              <div className="flex items-center gap-1">
                {scenario.trend === 'up' ? (
                  <TrendingUp className="w-4 h-4 text-accent" />
                ) : scenario.trend === 'down' ? (
                  <TrendingDown className="w-4 h-4 text-red-500" />
                ) : (
                  <Minus className="w-4 h-4 text-secondary" />
                )}
                <span className={scenario.trend === 'up' ? 'text-accent font-medium' : scenario.trend === 'down' ? 'text-red-600 dark:text-red-400 font-medium' : 'text-secondary font-medium'}>
                  {scenario.growth_rate_percent}%
                </span>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
