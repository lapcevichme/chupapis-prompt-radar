import {useMemo, useState} from 'react';
import {Clock, Coins, Percent, Wallet} from 'lucide-react';
import {Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import type {RoiData} from '@/entities/roi/types';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';
import {formatCurrencyRub, formatPercent} from '@/shared/lib/format';
import {Badge} from '@/shared/ui/Badge';
import {Card, CardContent, CardHeader, CardTitle} from '@/shared/ui/Card';
import {Pagination} from '@/shared/ui/Pagination';
import {EmptyState, ErrorState, LoadingState} from '@/widgets/data-state/DataState';

interface RoiPageProps {
  refreshKey: number;
}

const SCENARIOS_PER_PAGE = 3;

export default function RoiPage({refreshKey}: RoiPageProps) {
  const {data, error, isLoading} = useApiResource(() => promptRadarApi.getRoi(), [refreshKey]);

  if (isLoading) {
    return <LoadingState title="Loading ROI analytics" />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!data) {
    return <EmptyState title="No ROI data found" />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-secondary">
          FTE rate {formatCurrencyRub(data.assumptions.fte_hourly_rate_rub)}/h · token cost {data.assumptions.token_cost_per_1k_rub} RUB per 1k
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard icon={Wallet} label="Net Savings" value={formatCurrencyRub(data.summary.net_savings_rub)} detail={`ROI Multiplier: ${data.summary.roi_multiplier}x`} accent />
        <MetricCard icon={Clock} label="FTE Hours Saved" value={`${data.summary.total_fte_hours_saved}h`} detail="Manual labor equivalent" />
        <MetricCard icon={Coins} label="Agent Cost" value={formatCurrencyRub(data.summary.total_agent_cost_rub)} detail={`${data.summary.total_tokens_consumed.toLocaleString()} tokens`} />
        <MetricCard icon={Percent} label="Automation Rate" value={formatPercent(data.summary.process_automation_rate)} detail="End-to-end task completion" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="flex h-full min-h-[500px] flex-col">
          <CardHeader>
            <CardTitle>Savings by Category</CardTitle>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1">
            <CategorySavingsBars categories={data.by_category} />
          </CardContent>
        </Card>

        <TopScenarioRoiPager scenarios={data.by_scenario} />
      </div>
    </div>
  );
}

function TopScenarioRoiPager({scenarios}: {scenarios: RoiData['by_scenario']}) {
  const [page, setPage] = useState(0);
  const totalPages = Math.max(1, Math.ceil(scenarios.length / SCENARIOS_PER_PAGE));
  const safePage = Math.min(page, totalPages - 1);
  const pageStart = safePage * SCENARIOS_PER_PAGE;
  const visibleScenarios = useMemo(
    () => scenarios.slice(pageStart, pageStart + SCENARIOS_PER_PAGE),
    [pageStart, scenarios],
  );
  const rangeStart = scenarios.length === 0 ? 0 : pageStart + 1;
  const rangeEnd = Math.min(pageStart + SCENARIOS_PER_PAGE, scenarios.length);

  return (
    <Card className="flex h-full min-h-[500px] flex-col">
      <CardHeader>
        <div>
          <CardTitle>Top Scenarios ROI</CardTitle>
          <p className="mt-2 text-sm text-secondary">
            {scenarios.length === 0 ? 'No scenario ROI yet' : `${rangeStart}-${rangeEnd} of ${scenarios.length}`}
          </p>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        {visibleScenarios.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-divider text-sm text-secondary">
            No scenario ROI yet
          </div>
        ) : (
          <div className="space-y-3">
            {visibleScenarios.map((scenario) => (
              <ScenarioRoiItem key={scenario.scenario_id} scenario={scenario} />
            ))}
          </div>
        )}
        <Pagination currentPage={safePage} totalPages={totalPages} onPageChange={setPage} ariaLabel="Top scenarios pagination" />
      </CardContent>
    </Card>
  );
}

function CategorySavingsBars({categories}: {categories: RoiData['by_category']}) {
  const sortedCategories = useMemo(
    () => [...categories].sort((left, right) => right.net_savings_rub - left.net_savings_rub),
    [categories],
  );

  if (sortedCategories.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-divider text-sm text-secondary">
        No category savings yet
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-[330px] flex-1 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={sortedCategories} margin={{top: 28, right: 12, left: 4, bottom: 8}} barCategoryGap="34%">
            <CartesianGrid vertical={false} stroke="var(--color-divider)" strokeDasharray="4 4" />
            <XAxis
              dataKey="label"
              axisLine={false}
              tickLine={false}
              tickMargin={12}
              height={44}
              stroke="var(--color-secondary)"
              tick={{fontSize: 12}}
              tickFormatter={truncateChartLabel}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tickMargin={8}
              width={64}
              stroke="var(--color-secondary)"
              tick={{fontSize: 12}}
              tickFormatter={formatCompactCurrency}
            />
            <Tooltip
              cursor={{fill: 'var(--color-accent-muted)'}}
              contentStyle={{
                borderRadius: '6px',
                border: '1px solid var(--color-divider)',
                backgroundColor: 'var(--color-surface)',
                color: 'var(--color-primary)',
                fontSize: '12px',
                boxShadow: '0 6px 16px rgba(0, 0, 0, 0.18)',
              }}
              formatter={(value) => [formatCurrencyRub(Number(value)), 'Net savings']}
              labelFormatter={(label) => String(label)}
            />
            <Bar dataKey="net_savings_rub" name="Net savings" fill="var(--color-accent)" radius={[6, 6, 0, 0]} maxBarSize={88}>
              {sortedCategories.length <= 4 && (
                <LabelList dataKey="net_savings_rub" position="top" offset={10} fill="var(--color-primary)" fontSize={11} formatter={formatCompactCurrency} />
              )}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-divider pt-4 text-xs text-secondary">
        <span>{sortedCategories.reduce((sum, category) => sum + category.count, 0).toLocaleString()} requests</span>
        <span>{formatPercent(averageSuccessRate(sortedCategories))} average success</span>
        <span>{sortedCategories.reduce((sum, category) => sum + category.fte_hours_saved, 0).toFixed(1)} FTE hours saved</span>
      </div>
    </div>
  );
}

function formatCompactCurrency(value: number) {
  return `${new Intl.NumberFormat('ru-RU', {notation: 'compact', maximumFractionDigits: 1}).format(value)} ₽`;
}

function truncateChartLabel(value: string) {
  return value.length > 16 ? `${value.slice(0, 15)}…` : value;
}

function averageSuccessRate(categories: RoiData['by_category']) {
  const totalCount = categories.reduce((sum, category) => sum + category.count, 0);

  if (totalCount === 0) {
    return 0;
  }

  return categories.reduce((sum, category) => sum + category.success_rate_percent * category.count, 0) / totalCount;
}

function ScenarioRoiItem({scenario}: {scenario: RoiData['by_scenario'][number]}) {
  return (
    <div className="flex min-h-24 items-center justify-between gap-4 rounded-md border border-divider bg-surface px-4 py-3 transition-colors hover:bg-surface-hover">
      <div className="min-w-0">
        <h4 className="truncate text-sm font-semibold text-primary">{scenario.name ?? 'Unnamed scenario'}</h4>
        <p className="mt-1 text-sm text-secondary">{scenario.fte_hours_saved} hours saved</p>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-base font-semibold text-accent">{formatCurrencyRub(scenario.net_savings_rub)}</div>
        <Badge variant="outline" className="mt-1 normal-case tracking-normal">
          {scenario.automation_potential ?? 'unknown'} potential
        </Badge>
      </div>
    </div>
  );
}

function MetricCard({icon: Icon, label, value, detail, accent = false}: {icon: typeof Wallet; label: string; value: string; detail: string; accent?: boolean}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-secondary">{label}</CardTitle>
        <Icon className="h-4 w-4 text-accent" />
      </CardHeader>
      <CardContent>
        <div className={`text-3xl font-semibold ${accent ? 'text-accent' : 'text-primary'}`}>{value}</div>
        <p className="text-sm text-secondary mt-1">{detail}</p>
      </CardContent>
    </Card>
  );
}
