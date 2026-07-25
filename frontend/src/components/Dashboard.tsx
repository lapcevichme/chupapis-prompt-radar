import React, { useState, useEffect } from 'react';
import { fetchDashboard, fetchRoi } from '../api';
import type { DashboardSummary, RoiData } from '../types';
import { Card, CardContent, CardHeader, CardTitle } from './ui/Card';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell } from 'recharts';
import { Activity, AlertTriangle, FileText, Target, Loader2, Users, Clock, Wallet, CheckCircle2 } from 'lucide-react';

const COLORS = ['#2563EB', '#635BFF', '#3B82F6', '#8B5CF6', '#0EA5E9', '#64748B'];

interface DashboardProps {
  onFetchSuccess?: (timestamp?: string) => void;
  refreshTrigger?: number;
}

export default function Dashboard({ onFetchSuccess, refreshTrigger }: DashboardProps) {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [roi, setRoi] = useState<RoiData | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = async (silent = false) => {
    try {
      if (!silent && !data) setLoading(true);
      // QNA §2.1 asks for MAU / freed FTE / payoff on the main screen, not only
      // on the ROI tab: those are the numbers a CTO opens the dashboard for.
      const [res, roiRes] = await Promise.all([
        fetchDashboard(),
        fetchRoi().catch(() => null),
      ]);
      setData(res);
      setRoi(roiRes);
      onFetchSuccess?.(res.generated_at);
    } catch (err) {
      console.error('Failed to load dashboard', err);
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

  if (loading || !data) {
    return (
      <div className="flex justify-center p-12">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(val);

  return (
    <div className="space-y-6">
      {roi && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-secondary">Окупаемость</CardTitle>
              <CheckCircle2 className={`h-4 w-4 ${roi.verdict.pays_off ? 'text-emerald-400' : 'text-amber-400'}`} />
            </CardHeader>
            <CardContent>
              <div className={`text-3xl font-semibold ${roi.verdict.pays_off ? 'text-emerald-400' : 'text-amber-400'}`}>
                ×{roi.verdict.ratio}
              </div>
              <p className="text-sm text-secondary mt-1">
                {roi.verdict.pays_off ? 'выгода превышает затраты' : 'затраты превышают выгоду'}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-secondary">MAU</CardTitle>
              <Users className="h-4 w-4 text-accent" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-semibold text-primary">{roi.summary.mau_count}</div>
              <p className="text-sm text-secondary mt-1">активных пользователей</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-secondary">Высвобождено FTE</CardTitle>
              <Clock className="h-4 w-4 text-accent" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-semibold text-primary">{roi.summary.total_fte_hours_saved} ч</div>
              <p className="text-sm text-secondary mt-1">
                ≈ {(roi.summary.total_fte_hours_saved / 168).toFixed(1)} чел.-мес.
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-secondary">Чистая выгода</CardTitle>
              <Wallet className="h-4 w-4 text-accent" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-semibold text-accent">{formatCurrency(roi.verdict.net_rub)}</div>
              <p className="text-sm text-secondary mt-1">B − A за период</p>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-secondary">Total Requests</CardTitle>
            <FileText className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold text-primary truncate" title={data.total_logs.toString()}>
              {data.total_logs.toLocaleString()}
            </div>
            <p className="text-sm text-secondary mt-1">For selected period</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-secondary">Success Rate</CardTitle>
            <Target className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold text-primary truncate" title={`${data.success_rate_percent}%`}>
              {Number(data.success_rate_percent).toFixed(1).replace(/\.0$/, '')}%
            </div>
            <p className="text-sm text-secondary mt-1">Completed successfully</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-secondary">Outliers</CardTitle>
            <AlertTriangle className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold text-primary truncate" title={data.outliers_summary.total_outliers_count.toString()}>
              {data.outliers_summary.total_outliers_count.toLocaleString()}
            </div>
            <p className="text-sm text-secondary mt-1 truncate" title={`${data.outliers_summary.outlier_percentage}% of total traffic`}>
              {Number(data.outliers_summary.outlier_percentage).toFixed(1).replace(/\.0$/, '')}% of total traffic
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-secondary">Failures</CardTitle>
            <Activity className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold text-primary truncate" title={data.failure_analysis.total_requests_with_failure_signals.toString()}>
              {data.failure_analysis.total_requests_with_failure_signals.toLocaleString()}
            </div>
            <p className="text-sm text-secondary mt-1 truncate" title={`${data.failure_analysis.failure_signal_percentage}% error rate`}>
              {Number(data.failure_analysis.failure_signal_percentage).toFixed(1).replace(/\.0$/, '')}% error rate
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="col-span-1 lg:col-span-2">
          <CardHeader>
            <CardTitle>Request Dynamics</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] w-full mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.dynamics} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--color-accent)" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="var(--color-accent)" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tickLine={false} axisLine={false} tickFormatter={(val) => new Date(val).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} fontSize={12} tickMargin={10} stroke="var(--color-secondary)" />
                  <YAxis tickLine={false} axisLine={false} fontSize={12} stroke="var(--color-secondary)" />
                  <CartesianGrid vertical={false} stroke="var(--color-divider)" strokeDasharray="4 4" />
                  <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid var(--color-divider)', backgroundColor: 'var(--color-surface)', color: 'var(--color-primary)', fontSize: '12px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }} />
                  <Area type="monotone" dataKey="count" stroke="var(--color-accent)" strokeWidth={2} fillOpacity={1} fill="url(#colorCount)" isAnimationActive={false} />
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
                  <Pie
                    data={data.by_category}
                    cx="50%"
                    cy="50%"
                    innerRadius={70}
                    outerRadius={90}
                    paddingAngle={2}
                    dataKey="count"
                    stroke="none"
                    isAnimationActive={false}
                  >
                    {data.by_category.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid var(--color-divider)', backgroundColor: 'var(--color-surface)', color: 'var(--color-primary)', fontSize: '12px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none flex-col">
                 <span className="text-3xl font-semibold text-primary">{data.total_logs}</span>
                 <span className="text-sm text-secondary mt-1">Total</span>
              </div>
            </div>
            <div className="mt-6 grid grid-cols-2 gap-3">
              {data.by_category.slice(0, 4).map((cat, i) => (
                <div key={cat.task_type} className="flex items-center text-sm font-medium">
                  <div className="w-2.5 h-2.5 rounded-full mr-2" style={{ backgroundColor: COLORS[i] }} />
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
