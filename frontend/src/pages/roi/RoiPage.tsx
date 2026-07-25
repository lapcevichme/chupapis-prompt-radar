import {useEffect, useMemo, useState} from 'react';
import {Building2, Clock, Coins, Download, Loader2, Mic, Percent, RotateCcw, UserCheck, Wallet} from 'lucide-react';
import {Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import type {RoiData} from '@/entities/roi/types';
import {promptRadarApi, type RoiQuery} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';
import {formatCurrencyRub, formatPercent} from '@/shared/lib/format';
import {Badge} from '@/shared/ui/Badge';
import {Card, CardContent, CardHeader, CardTitle} from '@/shared/ui/Card';
import {Pagination} from '@/shared/ui/Pagination';
import {EmptyState, ErrorState, LoadingState} from '@/widgets/data-state/DataState';
import type {WorkspaceFilters} from '@/entities/workspace/types';

interface RoiPageProps {
  filters: WorkspaceFilters;
  refreshKey: number;
}

const SCENARIOS_PER_PAGE = 3;

export default function RoiPage({filters, refreshKey}: RoiPageProps) {
  const [appliedOverrides, setAppliedOverrides] = useState<Pick<RoiQuery, 'fte_hourly_rate_rub' | 'token_cost_per_1k_rub'>>({});
  const [draftFteRate, setDraftFteRate] = useState('');
  const [draftTokenCost, setDraftTokenCost] = useState('');
  const [defaultRates, setDefaultRates] = useState<{fte: number; token: number} | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<'xlsx' | 'csv' | null>(null);
  const query = useMemo(() => ({...filters, ...appliedOverrides}), [appliedOverrides, filters]);
  const {data, error, isLoading} = useApiResource(() => promptRadarApi.getRoi(query), [query, refreshKey]);

  useEffect(() => {
    if (!data || defaultRates) {
      return;
    }
    const defaults = {
      fte: data.assumptions.fte_hourly_rate_rub,
      token: data.assumptions.token_cost_per_1k_rub,
    };
    setDefaultRates(defaults);
    setDraftFteRate(String(defaults.fte));
    setDraftTokenCost(String(defaults.token));
  }, [data, defaultRates]);

  const applyOverrides = () => {
    const fte = Number(draftFteRate);
    const token = Number(draftTokenCost);
    if (!Number.isFinite(fte) || fte <= 0 || !Number.isFinite(token) || token <= 0) {
      setActionError('Rates must be positive numbers');
      return;
    }
    setActionError(null);
    setAppliedOverrides({fte_hourly_rate_rub: fte, token_cost_per_1k_rub: token});
  };

  const resetOverrides = () => {
    setAppliedOverrides({});
    setActionError(null);
    if (defaultRates) {
      setDraftFteRate(String(defaultRates.fte));
      setDraftTokenCost(String(defaultRates.token));
    }
  };

  const exportRoi = async (format: 'xlsx' | 'csv') => {
    setExporting(format);
    setActionError(null);
    try {
      const result = await promptRadarApi.exportResults(format, query);
      downloadBlob(result.blob, result.filename);
    } catch (exportError) {
      setActionError(exportError instanceof Error ? exportError.message : 'Export failed');
    } finally {
      setExporting(null);
    }
  };

  if (isLoading) {
    return <LoadingState title="Loading ROI analytics" />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!data) {
    return <EmptyState title="No ROI data found" />;
  }

  const {summary} = data;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <h2 className="text-sm font-medium text-secondary">
          FTE rate {formatCurrencyRub(data.assumptions.fte_hourly_rate_rub)}/h · token cost {data.assumptions.token_cost_per_1k_rub} RUB per 1k
        </h2>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-xs font-medium text-secondary">
            FTE rate, RUB/h
            <input
              className="h-9 w-36 rounded-md border border-divider bg-surface px-3 text-sm text-primary outline-none focus:border-accent"
              min="0.01"
              step="0.01"
              type="number"
              value={draftFteRate}
              onChange={(event) => setDraftFteRate(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-secondary">
            Token cost / 1k
            <input
              className="h-9 w-36 rounded-md border border-divider bg-surface px-3 text-sm text-primary outline-none focus:border-accent"
              min="0.000001"
              step="0.001"
              type="number"
              value={draftTokenCost}
              onChange={(event) => setDraftTokenCost(event.target.value)}
            />
          </label>
          <button className="h-9 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:opacity-90" onClick={applyOverrides} type="button">
            Apply
          </button>
          <button
            aria-label="Reset ROI assumptions"
            className="inline-flex h-9 items-center gap-2 rounded-md border border-divider px-3 text-sm font-medium text-secondary hover:bg-surface-hover"
            onClick={resetOverrides}
            type="button"
          >
            <RotateCcw className="h-4 w-4" /> Reset
          </button>
          {(['xlsx', 'csv'] as const).map((format) => (
            <button
              key={format}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-divider bg-surface px-3 text-sm font-medium text-primary hover:bg-surface-hover disabled:opacity-60"
              disabled={exporting !== null}
              onClick={() => void exportRoi(format)}
              type="button"
            >
              {exporting === format ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              {format.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {actionError && <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">{actionError}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard icon={Wallet} label="Net Savings" value={formatCurrencyRub(summary.net_savings_rub)} detail={`ROI Multiplier: ${summary.roi_multiplier}x`} accent />
        <MetricCard icon={Clock} label="FTE Hours Saved" value={`${summary.total_fte_hours_saved}h`} detail="Manual labor equivalent" />
        <MetricCard icon={Coins} label="Agent Cost" value={formatCurrencyRub(summary.total_agent_cost_rub)} detail={`${summary.total_tokens_consumed.toLocaleString()} tokens`} />
        <MetricCard icon={Percent} label="Automation Rate" value={formatPercent(summary.process_automation_rate)} detail="End-to-end task completion" />
      </div>

      {summary.style_insight && (
        <div className="flex items-center gap-3 rounded-lg border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-primary">
          <Mic className="h-5 w-5 shrink-0 text-accent" />
          <span>{summary.style_insight}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="flex h-full min-h-[450px] flex-col">
          <CardHeader>
            <CardTitle>Savings by Category</CardTitle>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1">
            <CategorySavingsBars categories={data.by_category} />
          </CardContent>
        </Card>

        <TopScenarioRoiPager scenarios={data.by_scenario} />
      </div>

      {(summary.top_spenders && summary.top_spenders.length > 0) || (summary.department_costs && Object.keys(summary.department_costs).length > 0) ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {summary.top_spenders && summary.top_spenders.length > 0 && (
            <Card className="flex flex-col">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <UserCheck className="h-5 w-5 text-accent" />
                  Heavy Users (Top Spenders)
                </CardTitle>
                {summary.mau_count ? <Badge variant="outline">{summary.mau_count} MAU</Badge> : null}
              </CardHeader>
              <CardContent className="space-y-3">
                {summary.top_spenders.map((user) => (
                  <div key={user.user_id} className="flex items-center justify-between rounded-md border border-divider bg-surface px-4 py-3">
                    <div>
                      <h4 className="text-sm font-semibold text-primary">{user.name}</h4>
                      <p className="text-xs text-secondary">{user.department} · {user.requests_count} requests</p>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold text-primary">{formatCurrencyRub(user.cost_rub)}</div>
                      <div className="text-xs text-secondary">{user.tokens_consumed.toLocaleString()} tokens</div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {summary.department_costs && Object.keys(summary.department_costs).length > 0 && (
            <Card className="flex flex-col">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Building2 className="h-5 w-5 text-accent" />
                  Costs by Department
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {Object.entries(summary.department_costs).map(([dept, cost]) => (
                  <div key={dept} className="flex items-center justify-between rounded-md border border-divider bg-surface px-4 py-3">
                    <span className="text-sm font-medium text-primary">{dept}</span>
                    <span className="text-sm font-semibold text-accent">{formatCurrencyRub(cost)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      ) : null}
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
    <Card className="flex h-full min-h-[450px] flex-col">
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
      <div className="flex min-h-[300px] flex-1 w-full">
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

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
