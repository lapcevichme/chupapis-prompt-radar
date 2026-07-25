import React, { useState, useEffect } from 'react';
import { fetchRoi } from '../api';
import type { RoiData } from '../types';
import { Card, CardContent, CardHeader, CardTitle } from './ui/Card';
import { Badge } from './ui/Badge';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { Wallet, Clock, Coins, Percent, Loader2 } from 'lucide-react';

export default function RoiView() {
  const [data, setData] = useState<RoiData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchRoi()
      .then(setData)
      .catch((err) => console.error('Failed to load ROI', err))
      .finally(() => setLoading(false));
  }, []);

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-secondary">Business value and token economics</h2>
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
            <div className="space-y-4 mt-2">
              {data.by_scenario.map((scenario) => (
                <div key={scenario.scenario_id} className="flex items-center justify-between p-4 border border-divider rounded-lg hover:bg-surface-hover transition-colors">
                  <div>
                    <h4 className="font-medium text-primary">{scenario.name}</h4>
                    <p className="text-sm text-secondary mt-1">{scenario.fte_hours_saved} hours saved</p>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-lg text-accent">{formatCurrency(scenario.net_savings_rub)}</div>
                    <Badge variant="outline" className="mt-1">{scenario.automation_potential} potential</Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
