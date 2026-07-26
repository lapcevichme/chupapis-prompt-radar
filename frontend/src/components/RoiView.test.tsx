import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RoiView from './RoiView';
import * as api from '../api';

const base: Record<string, unknown> = {
  assumptions: {
    fte_hourly_rate_rub: 2380.95,
    token_cost_per_1k_rub: 0.139,
    manual_minutes_by_category: { code_help: 30 },
    manual_minutes_estimated_percent: 100,
    fte_rate_model: null,
    token_cost_model: null,
  },
  verdict: {
    benefit_rub: 1000, cost_rub: 100, net_rub: 900,
    ratio: 10, pays_off: true, headline: 'ИИ окупается',
  },
  summary: {
    total_logs: 10, success_rate_percent: 90, total_fte_hours_saved: 5,
    total_manual_cost_rub: 1000, total_agent_cost_rub: 100, net_savings_rub: 900,
    roi_multiplier: 10, total_tokens_consumed: 1000, wasted_tokens_on_errors: 0,
    token_value_index: 0.1, process_automation_rate: 50, top_tools_used: {}, mau_count: 3,
  },
  by_category: [],
};

afterEach(() => vi.restoreAllMocks());

describe('RoiView scenarios', () => {
  it('hides raw unnamed clusters instead of rendering "null potential" cards', async () => {
    // Before recompute the ML store holds one unnamed cluster per record.
    const by_scenario = Array.from({ length: 40 }, (_, i) => ({
      scenario_id: `data_analysis:cluster_${i}`,
      name: null, count: 1, fte_hours_saved: 1, net_savings_rub: 1,
      automation_potential: null,
    }));
    vi.spyOn(api, 'fetchRoi').mockResolvedValue({ ...base, by_scenario } as never);

    render(<RoiView />);

    expect(await screen.findByText(/Сценарии ещё не посчитаны/)).toBeInTheDocument();
    expect(screen.queryByText(/null/)).not.toBeInTheDocument();
  });

  it('caps named scenarios at ten', async () => {
    const by_scenario = Array.from({ length: 25 }, (_, i) => ({
      scenario_id: `s_${i}`, name: `Сценарий ${i}`, count: 1,
      fte_hours_saved: 1, net_savings_rub: 1, automation_potential: 'high',
    }));
    vi.spyOn(api, 'fetchRoi').mockResolvedValue({ ...base, by_scenario } as never);

    render(<RoiView />);

    await screen.findByText('Сценарий 0');
    expect(screen.queryByText('Сценарий 10')).not.toBeInTheDocument();
  });
});
