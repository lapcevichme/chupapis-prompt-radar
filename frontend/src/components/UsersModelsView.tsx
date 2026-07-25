import React, { useState, useEffect } from 'react';
import { Users, Cpu, AlertTriangle, ShieldCheck, Zap, Award, UserCheck, HelpCircle } from 'lucide-react';
import type { UserAnalyticsData, ModelAnalyticsData } from '../types';
import { fetchUserAnalytics, fetchModelAnalytics } from '../api';

interface UsersModelsViewProps {
  onFetchSuccess?: () => void;
  refreshTrigger?: number;
}

export default function UsersModelsView({ onFetchSuccess, refreshTrigger }: UsersModelsViewProps) {
  const [activeSubTab, setActiveSubTab] = useState<'users' | 'models'>('users');
  const [userData, setUserData] = useState<UserAnalyticsData | null>(null);
  const [modelData, setModelData] = useState<ModelAnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async (silent = false) => {
    try {
      if (!silent && !userData && !modelData) setLoading(true);
      const [uRes, mRes] = await Promise.all([
        fetchUserAnalytics(),
        fetchModelAnalytics(),
      ]);
      setUserData(uRes);
      setModelData(mRes);
      onFetchSuccess?.();
    } catch (err: any) {
      if (!silent) setError(err.message || 'Ошибка загрузки данных');
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

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin w-8 h-8 border-4 border-accent border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error || !userData || !modelData) {
    return (
      <div className="p-6 bg-surface border border-divider rounded-xl text-center">
        <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto mb-2" />
        <p className="text-secondary">{error || 'Не удалось загрузить аналитику пользователей и моделей.'}</p>
      </div>
    );
  }

  const { summary: uSummary, by_department: depts, users } = userData;
  const { summary: mSummary, models, task_fit } = modelData;

  return (
    <div className="space-y-6">
      {/* Header & Sub-tab Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-surface p-4 border border-divider rounded-xl">
        <div>
          <h2 className="text-xl font-bold text-primary flex items-center gap-2">
            <Users className="w-6 h-6 text-accent" />
            Аналитика Пользователей и Моделей
          </h2>
          <p className="text-sm text-secondary">
            Анализ стилей работы сотрудников, уровня вовлечённости и производительности моделей.
          </p>
        </div>
        <div className="flex bg-background p-1 border border-divider rounded-lg shrink-0">
          <button
            onClick={() => setActiveSubTab('users')}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-all ${
              activeSubTab === 'users'
                ? 'bg-accent text-white shadow-sm'
                : 'text-secondary hover:text-primary'
            }`}
          >
            <Users className="w-4 h-4" />
            Пользователи & Архетипы
          </button>
          <button
            onClick={() => setActiveSubTab('models')}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-all ${
              activeSubTab === 'models'
                ? 'bg-accent text-white shadow-sm'
                : 'text-secondary hover:text-primary'
            }`}
          >
            <Cpu className="w-4 h-4" />
            Модели & Маршрутизация
          </button>
        </div>
      </div>

      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-surface p-4 border border-divider rounded-xl">
          <div className="flex items-center justify-between text-secondary mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Всего пользователей</span>
            <UserCheck className="w-4 h-4 text-accent" />
          </div>
          <div className="text-2xl font-bold text-primary">{uSummary.total_users}</div>
          <div className="text-xs text-secondary mt-1">Активных (L7): <span className="font-medium text-emerald-400">{uSummary.active_users_l7}</span></div>
        </div>

        <div className="bg-surface p-4 border border-divider rounded-xl">
          <div className="flex items-center justify-between text-secondary mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Индекс Adoption</span>
            <Award className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-primary">{uSummary.avg_adoption_score}%</div>
          <div className="text-xs text-secondary mt-1">Уровень внедрения ИИ в рутину</div>
        </div>

        <div className="bg-surface p-4 border border-divider rounded-xl">
          <div className="flex items-center justify-between text-secondary mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Frustration Index</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-primary">{uSummary.avg_frustration_index}%</div>
          <div className="text-xs text-secondary mt-1">Средний уровень трудностей / ошибок</div>
        </div>

        <div className="bg-surface p-4 border border-divider rounded-xl">
          <div className="flex items-center justify-between text-secondary mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Экономия маршрутизации</span>
            <Zap className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold text-primary">{mSummary.potential_cost_reduction_percent}%</div>
          <div className="text-xs text-secondary mt-1">Потенциал оптимизации токенов</div>
        </div>
      </div>

      {activeSubTab === 'users' ? (
        <>
          {/* Personas Distribution */}
          <div className="bg-surface p-5 border border-divider rounded-xl space-y-3">
            <h3 className="text-md font-bold text-primary flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-accent" />
              Распределение по Архетипам Использования
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {uSummary.personas_distribution.map((p) => (
                <div key={p.persona} className="p-3 bg-background border border-divider rounded-lg">
                  <div className="text-xs text-secondary font-medium">{p.label}</div>
                  <div className="text-xl font-bold text-primary mt-1">{p.count} <span className="text-xs font-normal text-secondary">({p.percentage}%)</span></div>
                </div>
              ))}
            </div>
          </div>

          {/* Department Breakdown */}
          <div className="bg-surface p-5 border border-divider rounded-xl space-y-4">
            <h3 className="text-md font-bold text-primary">Аналитика по Отделам</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-primary">
                <thead className="bg-background border-b border-divider text-xs uppercase text-secondary">
                  <tr>
                    <th className="p-3">Департамент</th>
                    <th className="p-3">Сотрудников</th>
                    <th className="p-3">Запросов</th>
                    <th className="p-3">Сэкономлено (ч)</th>
                    <th className="p-3">Frustration Index</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-divider">
                  {depts.map((d) => (
                    <tr key={d.department} className="hover:bg-surface-hover transition-colors">
                      <td className="p-3 font-medium">{d.department}</td>
                      <td className="p-3">{d.users_count}</td>
                      <td className="p-3">{d.total_queries}</td>
                      <td className="p-3 text-emerald-400 font-medium">{d.avg_saved_hours} ч</td>
                      <td className="p-3">
                        <span className={`px-2 py-1 rounded text-xs font-semibold ${
                          d.frustration_index > 15 ? 'bg-amber-500/20 text-amber-400' : 'bg-emerald-500/20 text-emerald-400'
                        }`}>
                          {d.frustration_index}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Detailed User Table & Recommendations */}
          <div className="bg-surface p-5 border border-divider rounded-xl space-y-4">
            <h3 className="text-md font-bold text-primary">Цифровые Профили Сотрудников</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-primary">
                <thead className="bg-background border-b border-divider text-xs uppercase text-secondary">
                  <tr>
                    <th className="p-3">Сотрудник</th>
                    <th className="p-3">Отдел</th>
                    <th className="p-3">Архетип</th>
                    <th className="p-3">Запросов</th>
                    <th className="p-3">Saved Time</th>
                    <th className="p-3">Frustration Index</th>
                    <th className="p-3">Рекомендация ИИ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-divider">
                  {users.map((u) => (
                    <tr key={u.user_id} className="hover:bg-surface-hover transition-colors">
                      <td className="p-3">
                        <div className="font-semibold text-primary">{u.user_name}</div>
                        <div className="text-xs text-secondary">{u.user_id}</div>
                      </td>
                      <td className="p-3 text-secondary">{u.department}</td>
                      <td className="p-3">
                        <span className="px-2 py-1 bg-accent/15 text-accent rounded text-xs font-medium">
                          {u.persona_label}
                        </span>
                      </td>
                      <td className="p-3">{u.total_queries}</td>
                      <td className="p-3 text-emerald-400 font-medium">{u.saved_hours} ч</td>
                      <td className="p-3">
                        <span className={`px-2 py-1 rounded text-xs font-semibold ${
                          u.frustration_index > 15 ? 'bg-amber-500/20 text-amber-400' : 'bg-emerald-500/20 text-emerald-400'
                        }`}>
                          {u.frustration_index}%
                        </span>
                      </td>
                      <td className="p-3 text-xs text-secondary max-w-md">
                        {u.needs_guidance && <span className="inline-block mr-1 text-amber-400 font-bold">⚠️ Нужна помощь:</span>}
                        {u.recommendation}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <>
          {/* Smart Routing Insight Box */}
          <div className="bg-gradient-to-r from-accent/20 to-cyan-500/10 p-5 border border-accent/30 rounded-xl space-y-2">
            <div className="flex items-center gap-2 text-accent font-bold text-md">
              <Zap className="w-5 h-5" />
              ИИ-Рекомендация по Маршрутизации и Экономии Токенов
            </div>
            <p className="text-sm text-primary leading-relaxed">
              {mSummary.routing_recommendation}
            </p>
          </div>

          {/* Model Performance Matrix */}
          <div className="bg-surface p-5 border border-divider rounded-xl space-y-4">
            <h3 className="text-md font-bold text-primary">Матрица Производительности Моделей</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {models.map((m) => (
                <div key={m.model_id} className="p-4 bg-background border border-divider rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-bold text-primary text-base">{m.model_name}</h4>
                      <span className="text-xs text-secondary">Доля: {m.share_percentage}% ({m.total_queries} зап.)</span>
                    </div>
                    <span className={`px-2 py-1 rounded text-xs font-bold ${
                      m.cost_tier === 'premium' ? 'bg-purple-500/20 text-purple-400' : 'bg-cyan-500/20 text-cyan-400'
                    }`}>
                      {m.cost_tier.toUpperCase()}
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-center text-xs pt-2 border-t border-divider">
                    <div>
                      <div className="text-secondary">Latency</div>
                      <div className="font-semibold text-primary mt-1">{m.avg_latency_ms} ms</div>
                    </div>
                    <div>
                      <div className="text-secondary">Ошибки</div>
                      <div className={`font-semibold mt-1 ${m.failure_rate_percent > 5 ? 'text-amber-400' : 'text-emerald-400'}`}>
                        {m.failure_rate_percent}%
                      </div>
                    </div>
                    <div>
                      <div className="text-secondary">Токены</div>
                      <div className="font-semibold text-primary mt-1">{(m.total_tokens / 1000).toFixed(0)}k</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Model to Task Fit Table */}
          <div className="bg-surface p-5 border border-divider rounded-xl space-y-4">
            <h3 className="text-md font-bold text-primary">Категориальное Соответствие (Model-to-Task Fit)</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-primary">
                <thead className="bg-background border-b border-divider text-xs uppercase text-secondary">
                  <tr>
                    <th className="p-3">Категория Запроса</th>
                    <th className="p-3">Рекомендуемая Модель</th>
                    <th className="p-3">Количество Запросов</th>
                    <th className="p-3">Средняя Задержка</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-divider">
                  {task_fit.map((tf) => (
                    <tr key={tf.task_type} className="hover:bg-surface-hover transition-colors">
                      <td className="p-3 font-medium">{tf.label}</td>
                      <td className="p-3 text-accent font-semibold">{tf.recommended_model}</td>
                      <td className="p-3">{tf.queries_count}</td>
                      <td className="p-3 text-secondary">{tf.avg_latency_ms} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
