import React, { useState, useEffect } from 'react';
import { fetchRoi } from '../api';
import type { RoiData } from '../types';
import { Card, CardContent, CardHeader, CardTitle } from './ui/Card';
import { Badge } from './ui/Badge';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { Wallet, Clock, Coins, Percent, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react';

interface RoiViewProps {
  onFetchSuccess?: () => void;
  refreshTrigger?: number;
}

export default function RoiView({ onFetchSuccess, refreshTrigger }: RoiViewProps) {
  const [data, setData] = useState<RoiData | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = async (silent = false) => {
    try {
      if (!silent && !data) setLoading(true);
      const res = await fetchRoi();
      setData(res);
      onFetchSuccess?.();
    } catch (err) {
      console.error('Failed to load ROI', err);
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

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(val);
  };

  if (loading || !data) {
    return (
      <div className="flex justify-center p-12">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  const fteModel = data.assumptions.fte_rate_model;
  const tokenModel = data.assumptions.token_cost_model;

  // Before heavy recompute the ML store holds one raw online cluster per record:
  // unnamed and unsummarized. Those are pipeline internals, not scenarios — the
  // Scenarios screen already hides them, and ROI must not render them either.
  const namedScenarios = data.by_scenario
    .filter((s) => s.name && s.name.trim().length > 0)
    .slice(0, 10);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-secondary">Business value and token economics</h2>
      </div>

      {/* QNA §1: the customer's expert asks for an explicit "does it pay off?"
          verdict, not a number the reader has to compare in their head. */}
      <div
        className={`p-5 border rounded-xl ${
          data.verdict.pays_off
            ? 'border-emerald-500/30 bg-emerald-500/10'
            : 'border-amber-500/30 bg-amber-500/10'
        }`}
      >
        <div className="flex items-center gap-2 mb-3">
          {data.verdict.pays_off
            ? <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
            : <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />}
          <span className={`font-semibold ${data.verdict.pays_off ? 'text-emerald-400' : 'text-amber-400'}`}>
            {data.verdict.headline}
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="p-3 bg-surface/60 border border-divider rounded-lg">
            <div className="text-xs text-secondary uppercase tracking-wider">B — выгода</div>
            <div className="text-lg font-semibold text-primary mt-1">{formatCurrency(data.verdict.benefit_rub)}</div>
            <div className="text-xs text-secondary">высвобожденные FTE-часы × ставка</div>
          </div>
          <div className="p-3 bg-surface/60 border border-divider rounded-lg">
            <div className="text-xs text-secondary uppercase tracking-wider">A — затраты</div>
            <div className="text-lg font-semibold text-primary mt-1">{formatCurrency(data.verdict.cost_rub)}</div>
            <div className="text-xs text-secondary">токены × себестоимость инфраструктуры</div>
          </div>
          <div className="p-3 bg-surface/60 border border-divider rounded-lg">
            <div className="text-xs text-secondary uppercase tracking-wider">B − A</div>
            <div className={`text-lg font-semibold mt-1 ${data.verdict.pays_off ? 'text-emerald-400' : 'text-amber-400'}`}>
              {formatCurrency(data.verdict.net_rub)}
            </div>
            <div className="text-xs text-secondary">окупаемость ×{data.verdict.ratio}</div>
          </div>
        </div>
      </div>

      {/* Every number above is an estimate under stated premises. Show the
          premises next to it so the figure can be argued with, not just trusted. */}
      <div className="p-4 border border-divider rounded-lg bg-surface text-xs text-secondary space-y-2">
        <div className="font-medium text-primary text-sm">Предпосылки расчёта</div>

        {fteModel && (
          <div>
            <span className="text-primary">Ставка FTE:</span>{' '}
            {fteModel.monthly_rate_rub.toLocaleString('ru-RU')} ₽/мес ÷{' '}
            {fteModel.work_hours_per_month} ч ={' '}
            <span className="text-primary font-medium">
              {data.assumptions.fte_hourly_rate_rub.toFixed(0)} ₽/ч
            </span>
            {fteModel.is_overridden && <span className="text-amber-400"> · переопределено вручную</span>}
          </div>
        )}

        {tokenModel && (
          <div>
            <span className="text-primary">Себестоимость токена:</span>{' '}
            ({tokenModel.infra_capex_rub.toLocaleString('ru-RU')} ₽ ÷ {tokenModel.amortization_years} лет +{' '}
            {tokenModel.electricity_rub_per_year.toLocaleString('ru-RU')} ₽/год электричество) ÷{' '}
            {(tokenModel.tokens_per_year / 1e9).toFixed(0)} млрд токенов/год ={' '}
            <span className="text-primary font-medium">
              {data.assumptions.token_cost_per_1k_rub.toFixed(3)} ₽ / 1k
            </span>
            {tokenModel.is_overridden && <span className="text-amber-400"> · переопределено вручную</span>}
          </div>
        )}

        {data.assumptions.manual_minutes_estimated_percent > 0 && (
          <div>
            <span className="text-primary">Время ручной работы:</span> у{' '}
            {data.assumptions.manual_minutes_estimated_percent}% записей оно не замерено — использован
            норматив по категории (
            {Object.entries(data.assumptions.manual_minutes_by_category)
              .map(([k, v]) => `${k} ${v}м`)
              .join(' · ')}
            ).
          </div>
        )}

        <div className="pt-1 border-t border-divider text-secondary">
          Это оценка при названных предпосылках, а не измеренный факт. Ставки меняются
          параметрами запроса <code className="text-accent">?fte_hourly_rate_rub=</code> и{' '}
          <code className="text-accent">?token_cost_per_1k_rub=</code>.
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-secondary">Net Savings</CardTitle>
            <Wallet className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold text-accent">{formatCurrency(data.summary.net_savings_rub)}</div>
            <p className="text-sm text-secondary mt-1">ROI Multiplier: {data.summary.roi_multiplier}x</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-secondary">FTE Hours Saved</CardTitle>
            <Clock className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold text-primary">{data.summary.total_fte_hours_saved}h</div>
            <p className="text-sm text-secondary mt-1">Manual labor equivalent</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-secondary">Agent Cost</CardTitle>
            <Coins className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold text-primary">{formatCurrency(data.summary.total_agent_cost_rub)}</div>
            <p className="text-sm text-secondary mt-1">{data.summary.total_tokens_consumed.toLocaleString()} tokens</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-secondary">Automation Rate</CardTitle>
            <Percent className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold text-primary">{data.summary.process_automation_rate}%</div>
            <p className="text-sm text-secondary mt-1">End-to-end task completion</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Savings by Category</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] w-full mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.by_category} layout="vertical" margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="var(--color-divider)" />
                  <XAxis type="number" tickFormatter={(val) => `₽${(val/1000)}k`} fontSize={12} stroke="var(--color-secondary)" tickLine={false} axisLine={false} />
                  <YAxis dataKey="label" type="category" axisLine={false} tickLine={false} fontSize={12} stroke="var(--color-secondary)" width={100} />
                  <Tooltip cursor={{fill: 'var(--color-surface-hover)'}} contentStyle={{ borderRadius: '8px', border: '1px solid var(--color-divider)', backgroundColor: 'var(--color-surface)', color: 'var(--color-primary)', fontSize: '12px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }} formatter={(value: number) => formatCurrency(value)} />
                  <Bar dataKey="net_savings_rub" fill="var(--color-accent)" radius={[0, 4, 4, 0]} barSize={32} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top Scenarios ROI</CardTitle>
          </CardHeader>
          <CardContent>
            {namedScenarios.length === 0 ? (
              <div className="mt-2 p-6 border border-dashed border-divider rounded-lg text-center space-y-1">
                <p className="text-sm text-primary font-medium">Сценарии ещё не посчитаны</p>
                <p className="text-sm text-secondary">
                  Запустите Recompute — он соберёт кластеры в именованные сценарии
                  с саммари. До этого ROI доступен в разрезе категорий.
                </p>
              </div>
            ) : (
              <div className="space-y-4 mt-2">
                {namedScenarios.map((scenario) => (
                  <div key={scenario.scenario_id} className="flex items-center justify-between p-4 border border-divider rounded-lg hover:bg-surface-hover transition-colors">
                    <div>
                      <h4 className="font-medium text-primary">{scenario.name}</h4>
                      <p className="text-sm text-secondary mt-1">{scenario.fte_hours_saved} hours saved</p>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold text-lg text-accent">{formatCurrency(scenario.net_savings_rub)}</div>
                      {scenario.automation_potential && (
                        <Badge variant="outline" className="mt-1">{scenario.automation_potential} potential</Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
