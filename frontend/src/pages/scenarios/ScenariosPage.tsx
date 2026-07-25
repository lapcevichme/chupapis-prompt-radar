import {useEffect, useMemo, useState} from 'react';
import {Bot, ChevronDown, Loader2, Minus, Target, TrendingDown, TrendingUp} from 'lucide-react';
import type {Scenario} from '@/entities/scenario/types';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';
import {formatPercent, titleFromCode} from '@/shared/lib/format';
import {cn} from '@/shared/lib/cn';
import {Badge} from '@/shared/ui/Badge';
import {Card, CardContent, CardHeader, CardTitle} from '@/shared/ui/Card';
import {EmptyState, ErrorState, LoadingState} from '@/widgets/data-state/DataState';
import type {WorkspaceFilters} from '@/entities/workspace/types';

interface ScenariosPageProps {
  filters: WorkspaceFilters;
  refreshKey: number;
}

export default function ScenariosPage({filters, refreshKey}: ScenariosPageProps) {
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [taskType, setTaskType] = useState('');
  const {data, error, isLoading} = useApiResource(() => promptRadarApi.getScenarios(filters), [filters, refreshKey]);
  const scenarioDetailState = useApiResource<Scenario | null>(
    () => (selectedScenarioId ? promptRadarApi.getScenario(selectedScenarioId) : Promise.resolve(null)),
    [selectedScenarioId, refreshKey],
  );
  const allScenarios = data?.items ?? [];
  const taskTypes = useMemo(
    () => [...new Set(allScenarios.map((scenario) => scenario.task_type).filter((value): value is string => Boolean(value)))].sort(),
    [allScenarios],
  );
  const scenarios = taskType ? allScenarios.filter((scenario) => scenario.task_type === taskType) : allScenarios;

  useEffect(() => {
    if (taskType && !taskTypes.includes(taskType)) {
      setTaskType('');
    }
  }, [taskType, taskTypes]);

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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-sm font-medium text-secondary">{scenarios.length} auto-discovered user interaction clusters</h2>
        <select
          className="h-9 rounded-md border border-divider bg-surface px-3 text-sm text-primary outline-none focus:border-accent"
          value={taskType}
          onChange={(event) => setTaskType(event.target.value)}
        >
          <option value="">All task types</option>
          {taskTypes.map((value) => <option key={value} value={value}>{titleFromCode(value)}</option>)}
        </select>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="grid auto-rows-min grid-cols-1 gap-4 md:grid-cols-2">
          {scenarios.map((scenario) => (
            <button
              key={scenario.scenario_id}
              type="button"
              className="text-left"
              onClick={() => setSelectedScenarioId(scenario.scenario_id)}
            >
              <Card
                className={cn(
                  'transition-colors hover:border-accent/50',
                  scenario.scenario_id === selectedScenarioId && 'border-accent bg-accent-muted/10',
                )}
              >
                <CardHeader className="p-5 pb-3">
                  <div className="mb-3 flex items-start justify-between gap-3">
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
                <CardContent className="p-5 pt-0">
                  <div className="rounded-md border border-divider bg-background/30 p-3">
                    <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-secondary">
                      <Target className="h-3.5 w-3.5" /> User Goal
                    </div>
                    <p className="line-clamp-2 text-sm text-primary">{scenario.user_goal ?? 'Not defined'}</p>
                  </div>
                </CardContent>
                <div className="flex items-center justify-between rounded-b-lg border-t border-divider bg-surface-hover px-5 py-3 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-primary">{scenario.count}</span>
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
  const [areExamplesExpanded, setAreExamplesExpanded] = useState(false);

  useEffect(() => {
    setAreExamplesExpanded(false);
  }, [scenario?.scenario_id]);

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

            <RepresentativeExamples
              items={scenario.representative_examples}
              isExpanded={areExamplesExpanded}
              onToggle={() => setAreExamplesExpanded((value) => !value)}
            />
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

function RepresentativeExamples({
  items,
  isExpanded,
  onToggle,
}: {
  items: string[];
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="space-y-3 border-t border-divider pt-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-primary">Representative Examples</h4>
          <p className="mt-1 text-xs text-secondary">
            {items.length > 0 ? `${items.length} prompts hidden` : 'No examples available'}
          </p>
        </div>
        {items.length > 0 && (
          <button
            type="button"
            className="inline-flex h-8 items-center gap-1 rounded-md border border-divider px-2.5 text-xs font-semibold text-primary hover:bg-surface-hover"
            onClick={onToggle}
          >
            {isExpanded ? 'Hide' : 'Show'}
            <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', isExpanded && 'rotate-180')} />
          </button>
        )}
      </div>

      {items.length > 0 && isExpanded && (
        <ul className="max-h-[300px] space-y-2 overflow-y-auto pr-1">
          {items.slice(0, 5).map((item) => (
            <li key={item} className="rounded-md bg-background/40 p-3 text-sm leading-relaxed text-primary">
              {item}
            </li>
          ))}
        </ul>
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
