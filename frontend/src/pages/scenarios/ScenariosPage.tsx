import {useEffect, useState} from 'react';
import {Bot, Loader2, Minus, Target, TrendingDown, TrendingUp} from 'lucide-react';
import type {Scenario} from '@/entities/scenario/types';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';
import {formatPercent, titleFromCode} from '@/shared/lib/format';
import {cn} from '@/shared/lib/cn';
import {Badge} from '@/shared/ui/Badge';
import {Card, CardContent, CardHeader, CardTitle} from '@/shared/ui/Card';
import {EmptyState, ErrorState, LoadingState} from '@/widgets/data-state/DataState';

interface ScenariosPageProps {
  refreshKey: number;
}

export default function ScenariosPage({refreshKey}: ScenariosPageProps) {
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const {data, error, isLoading} = useApiResource(() => promptRadarApi.getScenarios(), [refreshKey]);
  const scenarioDetailState = useApiResource<Scenario | null>(
    () => (selectedScenarioId ? promptRadarApi.getScenario(selectedScenarioId) : Promise.resolve(null)),
    [selectedScenarioId, refreshKey],
  );
  const scenarios = data?.items ?? [];

  useEffect(() => {
    if (scenarios.length === 0) {
      setSelectedScenarioId(null);
      return;
    }

    if (!selectedScenarioId || !scenarios.some((scenario) => scenario.scenario_id === selectedScenarioId)) {
      setSelectedScenarioId(scenarios[0].scenario_id);
    }
  }, [scenarios, selectedScenarioId]);

  if (isLoading) {
    return <LoadingState title="Loading scenarios" />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!data || scenarios.length === 0) {
    return <EmptyState title="No scenarios found" />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-secondary">{data.total} auto-discovered user interaction clusters</h2>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {scenarios.map((scenario) => (
            <button
              key={scenario.scenario_id}
              type="button"
              className="h-full text-left"
              onClick={() => setSelectedScenarioId(scenario.scenario_id)}
            >
              <Card
                className={cn(
                  'flex h-full flex-col transition-colors hover:border-accent/50',
                  scenario.scenario_id === selectedScenarioId && 'border-accent bg-accent-muted/10',
                )}
              >
                <CardHeader className="pb-4">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <Badge variant="secondary">{titleFromCode(scenario.task_type)}</Badge>
                    {scenario.automation_potential === 'high' && (
                      <Badge variant="success" className="flex items-center gap-1">
                        <Bot className="w-3 h-3" />
                        High ROI
                      </Badge>
                    )}
                  </div>
                  <CardTitle className="text-primary">{scenario.name ?? 'Unnamed scenario'}</CardTitle>
                  <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-secondary">{scenario.summary ?? 'No summary available'}</p>
                </CardHeader>
                <CardContent className="flex-1">
                  <div className="space-y-5">
                    <div>
                      <div className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-secondary">
                        <Target className="w-3.5 h-3.5" /> User Goal
                      </div>
                      <p className="line-clamp-2 text-sm text-primary">{scenario.user_goal ?? 'Not defined'}</p>
                    </div>
                    <div>
                      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-secondary">Pain Points</div>
                      {scenario.pain_points.length > 0 ? (
                        <ul className="space-y-1 text-sm text-primary">
                          {scenario.pain_points.slice(0, 2).map((point) => (
                            <li key={point} className="truncate">
                              {point}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-secondary">No pain points detected</p>
                      )}
                    </div>
                  </div>
                </CardContent>
                <div className="flex items-center justify-between rounded-b-lg border-t border-divider bg-surface-hover p-4 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-semibold text-primary">{scenario.count}</span>
                    <span className="text-secondary">requests</span>
                  </div>
                  <Trend trend={scenario.trend} growth={scenario.growth_rate_percent} />
                </div>
              </Card>
            </button>
          ))}
        </div>

        <ScenarioDetailsPanel
          scenario={scenarioDetailState.data}
          isLoading={scenarioDetailState.isLoading}
          error={scenarioDetailState.error}
        />
      </div>
    </div>
  );
}

function ScenarioDetailsPanel({
  scenario,
  isLoading,
  error,
}: {
  scenario: Scenario | null;
  isLoading: boolean;
  error: string | null;
}) {
  return (
    <Card className="min-h-[520px]">
      <CardHeader>
        <CardTitle>Scenario Details</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="flex min-h-[360px] items-center justify-center gap-3 text-sm font-medium text-secondary">
            <Loader2 className="h-5 w-5 animate-spin text-accent" />
            Loading scenario
          </div>
        )}
        {!isLoading && error && (
          <div className="rounded-md border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">{error}</div>
        )}
        {!isLoading && !error && !scenario && (
          <div className="flex min-h-[360px] flex-col items-center justify-center text-center">
            <Target className="mb-4 h-12 w-12 text-secondary/60" />
            <p className="text-sm text-secondary">Select a scenario to inspect details</p>
          </div>
        )}
        {!isLoading && !error && scenario && (
          <div className="space-y-6">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">{titleFromCode(scenario.task_type)}</Badge>
                {scenario.statistical_reliability && <Badge variant="outline">{scenario.statistical_reliability} reliability</Badge>}
              </div>
              <div>
                <h3 className="text-xl font-semibold text-primary">{scenario.name ?? 'Unnamed scenario'}</h3>
                <p className="mt-1 break-all text-xs text-secondary">{scenario.scenario_id}</p>
              </div>
              <p className="text-sm leading-relaxed text-secondary">{scenario.summary ?? 'No summary available'}</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <ScenarioMetric label="Requests" value={scenario.count.toLocaleString()} />
              <ScenarioMetric label="Potential" value={scenario.automation_potential ?? 'Unknown'} />
            </div>

            <div className="space-y-3 border-t border-divider pt-5">
              <h4 className="text-sm font-semibold text-primary">User Goal</h4>
              <p className="text-sm leading-relaxed text-primary">{scenario.user_goal ?? 'Not defined'}</p>
            </div>

            <DetailList title="Representative Examples" items={scenario.representative_examples} emptyText="No examples available" />
            <DetailList title="Pain Points" items={scenario.pain_points} emptyText="No pain points detected" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ScenarioMetric({label, value}: {label: string; value: string}) {
  return (
    <div className="rounded-md border border-divider bg-background/40 p-3">
      <div className="text-xs text-secondary">{label}</div>
      <div className="mt-1 truncate text-lg font-semibold text-primary">{value}</div>
    </div>
  );
}

function DetailList({title, items, emptyText}: {title: string; items: string[]; emptyText: string}) {
  return (
    <div className="space-y-3 border-t border-divider pt-5">
      <h4 className="text-sm font-semibold text-primary">{title}</h4>
      {items.length > 0 ? (
        <ul className="space-y-2">
          {items.slice(0, 5).map((item) => (
            <li key={item} className="rounded-md bg-background/40 p-3 text-sm leading-relaxed text-primary">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-secondary">{emptyText}</p>
      )}
    </div>
  );
}

function Trend({trend, growth}: {trend: string | null; growth: number | null}) {
  if (trend === 'up') {
    return (
      <div className="flex items-center gap-1 text-accent font-medium">
        <TrendingUp className="w-4 h-4" />
        <span>{formatPercent(growth)}</span>
      </div>
    );
  }

  if (trend === 'down') {
    return (
      <div className="flex items-center gap-1 text-red-600 dark:text-red-400 font-medium">
        <TrendingDown className="w-4 h-4" />
        <span>{formatPercent(growth)}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1 text-secondary font-medium">
      <Minus className="w-4 h-4" />
      <span>{formatPercent(growth)}</span>
    </div>
  );
}
