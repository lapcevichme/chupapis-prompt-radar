import {Activity, AlertTriangle, FileText, Target} from 'lucide-react';
import {Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {useApiResource} from '@/shared/api/useApiResource';
import {formatDateTime, formatPercent} from '@/shared/lib/format';
import {Card, CardContent, CardHeader, CardTitle} from '@/shared/ui/Card';
import {EmptyState, ErrorState, LoadingState} from '@/widgets/data-state/DataState';
import type {WorkspaceFilters} from '@/entities/workspace/types';

const COLORS = ['#2563EB', '#635BFF', '#3B82F6', '#8B5CF6', '#0EA5E9', '#64748B'];

interface DashboardPageProps {
  filters: WorkspaceFilters;
  refreshKey: number;
}

export default function DashboardPage({filters, refreshKey}: DashboardPageProps) {
  const {data, error, isLoading} = useApiResource(() => promptRadarApi.getDashboard(filters), [filters, refreshKey]);

  if (isLoading) {
    return <LoadingState title="Loading dashboard" />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!data) {
    return <EmptyState title="Dashboard has no data" />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <p className="text-sm text-secondary">
          Taxonomy {data.taxonomy_version} · last recompute {formatDateTime(data.freshness.last_recompute_at)}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard icon={FileText} label="Total Requests" value={data.total_logs.toLocaleString()} detail="Processed records" />
        <MetricCard icon={Target} label="Success Rate" value={formatPercent(data.success_rate_percent)} detail="Estimated from failure signals" />
        <MetricCard icon={AlertTriangle} label="Outliers" value={data.outliers_summary.total_outliers_count.toLocaleString()} detail={`${formatPercent(data.outliers_summary.outlier_percentage)} of total traffic`} />
        <MetricCard icon={Activity} label="Failures" value={data.failure_analysis.total_requests_with_failure_signals.toLocaleString()} detail={`${formatPercent(data.failure_analysis.failure_signal_percentage)} error rate`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="col-span-1 lg:col-span-2">
          <CardHeader>
            <CardTitle>Request Dynamics</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] w-full mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.dynamics} margin={{top: 10, right: 10, left: -20, bottom: 0}}>
                  <defs>
                    <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--color-accent)" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="var(--color-accent)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tickLine={false} axisLine={false} tickFormatter={(val) => new Date(val).toLocaleDateString('en-US', {month: 'short', day: 'numeric'})} fontSize={12} tickMargin={10} stroke="var(--color-secondary)" />
                  <YAxis tickLine={false} axisLine={false} fontSize={12} stroke="var(--color-secondary)" />
                  <CartesianGrid vertical={false} stroke="var(--color-divider)" strokeDasharray="4 4" />
                  <Tooltip contentStyle={{borderRadius: '8px', border: '1px solid var(--color-divider)', backgroundColor: 'var(--color-surface)', color: 'var(--color-primary)', fontSize: '12px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'}} />
                  <Area type="monotone" dataKey="count" stroke="var(--color-accent)" strokeWidth={2} fillOpacity={1} fill="url(#colorCount)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-1">
          <CardHeader>
            <CardTitle>By Category</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] w-full relative mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={data.by_category} cx="50%" cy="50%" innerRadius={70} outerRadius={90} paddingAngle={2} dataKey="count" stroke="none">
                    {data.by_category.map((entry, index) => (
                      <Cell key={entry.task_type} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{borderRadius: '8px', border: '1px solid var(--color-divider)', backgroundColor: 'var(--color-surface)', color: 'var(--color-primary)', fontSize: '12px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'}} />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none flex-col">
                <span className="text-3xl font-semibold text-primary">{data.total_logs.toLocaleString()}</span>
                <span className="text-sm text-secondary mt-1">Total</span>
              </div>
            </div>
            <div className="mt-6 grid grid-cols-2 gap-3">
              {data.by_category.slice(0, 4).map((cat, index) => (
                <div key={cat.task_type} className="flex items-center text-sm font-medium min-w-0">
                  <div className="w-2.5 h-2.5 rounded-full mr-2 shrink-0" style={{backgroundColor: COLORS[index]}} />
                  <span className="truncate text-secondary">{cat.label}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function MetricCard({icon: Icon, label, value, detail}: {icon: typeof FileText; label: string; value: string; detail: string}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-secondary">{label}</CardTitle>
        <Icon className="h-4 w-4 text-accent" />
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold text-primary">{value}</div>
        <p className="text-sm text-secondary mt-1">{detail}</p>
      </CardContent>
    </Card>
  );
}
