import {Bot, Minus, Target, TrendingDown, TrendingUp} from 'lucide-react';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';
import {formatPercent, titleFromCode} from '@/shared/lib/format';
import {Badge} from '@/shared/ui/Badge';
import {Card, CardContent, CardHeader, CardTitle} from '@/shared/ui/Card';
import {EmptyState, ErrorState, LoadingState} from '@/widgets/data-state/DataState';

interface ScenariosPageProps {
  refreshKey: number;
}

export default function ScenariosPage({refreshKey}: ScenariosPageProps) {
  const {data, error, isLoading} = useApiResource(() => promptRadarApi.getScenarios(), [refreshKey]);

  if (isLoading) {
    return <LoadingState title="Loading scenarios" />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!data || data.items.length === 0) {
    return <EmptyState title="No scenarios found" />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-secondary">{data.total} auto-discovered user interaction clusters</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {data.items.map((scenario) => (
          <Card key={scenario.scenario_id} className="flex flex-col hover:border-accent/50 transition-colors group">
            <CardHeader className="pb-4">
              <div className="flex justify-between items-start gap-3 mb-3">
                <Badge variant="secondary">{titleFromCode(scenario.task_type)}</Badge>
                {scenario.automation_potential === 'high' && (
                  <Badge variant="success" className="flex items-center gap-1">
                    <Bot className="w-3 h-3" />
                    High ROI
                  </Badge>
                )}
              </div>
              <CardTitle className="text-primary group-hover:text-accent transition-colors">{scenario.name ?? 'Unnamed scenario'}</CardTitle>
              <p className="text-sm text-secondary line-clamp-2 mt-2 leading-relaxed">{scenario.summary ?? 'No summary available'}</p>
            </CardHeader>
            <CardContent className="flex-1">
              <div className="space-y-5">
                <div>
                  <div className="text-xs font-semibold text-secondary uppercase tracking-wider mb-2 flex items-center gap-1">
                    <Target className="w-3.5 h-3.5" /> User Goal
                  </div>
                  <p className="text-sm text-primary">{scenario.user_goal ?? 'Not defined'}</p>
                </div>
                <div>
                  <div className="text-xs font-semibold text-secondary uppercase tracking-wider mb-2">Pain Points</div>
                  {scenario.pain_points.length > 0 ? (
                    <ul className="text-sm text-primary list-disc list-inside space-y-1">
                      {scenario.pain_points.map((point) => (
                        <li key={point}>{point}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-secondary">No pain points detected</p>
                  )}
                </div>
              </div>
            </CardContent>
            <div className="p-4 border-t border-divider bg-surface-hover flex justify-between items-center text-sm rounded-b-lg">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-primary text-lg">{scenario.count}</span>
                <span className="text-secondary">requests</span>
              </div>
              <Trend trend={scenario.trend} growth={scenario.growth_rate_percent} />
            </div>
          </Card>
        ))}
      </div>
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
