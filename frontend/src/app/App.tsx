import {useCallback, useEffect, useState} from 'react';
import {Activity, Database, DollarSign, LayoutDashboard, Target} from 'lucide-react';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {ApiError} from '@/shared/api/http';
import {DEMO_EMAIL, DEMO_PASSWORD, FALLBACK_DEMO_EMAIL, FALLBACK_DEMO_PASSWORD} from '@/shared/config/env';
import type {User} from '@/entities/user/types';
import DashboardPage from '@/pages/dashboard/DashboardPage';
import LogsPage from '@/pages/logs/LogsPage';
import RoiPage from '@/pages/roi/RoiPage';
import ScenariosPage from '@/pages/scenarios/ScenariosPage';
import SourcesPage from '@/pages/sources/SourcesPage';
import {AppShell, type NavItem} from '@/widgets/app-shell/AppShell';
import {ErrorState, LoadingState} from '@/widgets/data-state/DataState';

type TabId = 'dashboard' | 'sources' | 'scenarios' | 'logs' | 'roi';

const navItems: NavItem<TabId>[] = [
  {id: 'dashboard', label: 'Overview', icon: LayoutDashboard},
  {id: 'sources', label: 'Ingestion & Sources', icon: Database},
  {id: 'scenarios', label: 'Scenarios', icon: Target},
  {id: 'logs', label: 'Logs & Outliers', icon: Activity},
  {id: 'roi', label: 'ROI Analytics', icon: DollarSign},
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('dashboard');
  const [isDark, setIsDark] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  const refreshData = useCallback(() => {
    setRefreshKey((key) => key + 1);
  }, []);

  const bootstrapAuth = useCallback(async () => {
    setIsBootstrapping(true);
    setAuthError(null);

    try {
      try {
        setUser(await promptRadarApi.getMe());
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) {
          throw error;
        }

        const credentials = [
          {email: DEMO_EMAIL, password: DEMO_PASSWORD},
          {email: FALLBACK_DEMO_EMAIL, password: FALLBACK_DEMO_PASSWORD},
        ];
        let lastError: unknown = error;

        for (const credential of credentials) {
          try {
            const loginResponse = await promptRadarApi.login(credential);
            setUser(loginResponse.user);
            return;
          } catch (loginError) {
            lastError = loginError;
          }
        }

        throw lastError;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Authorization failed';
      setAuthError(message);
    } finally {
      setIsBootstrapping(false);
    }
  }, []);

  useEffect(() => {
    void bootstrapAuth();
  }, [bootstrapAuth]);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
  }, [isDark]);

  if (isBootstrapping) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <LoadingState title="Connecting to backend" />
      </div>
    );
  }

  if (authError || !user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <ErrorState
          title="Backend authorization failed"
          message={authError ?? 'No active user session'}
          actionLabel="Retry"
          onAction={() => void bootstrapAuth()}
        />
      </div>
    );
  }

  return (
    <AppShell<TabId>
      activeTab={activeTab}
      isDark={isDark}
      navItems={navItems}
      user={user}
      onRefresh={refreshData}
      onSelectTab={(tab) => setActiveTab(tab)}
      onToggleTheme={() => setIsDark((value) => !value)}
    >
      {activeTab === 'dashboard' && <DashboardPage refreshKey={refreshKey} />}
      {activeTab === 'sources' && <SourcesPage refreshKey={refreshKey} onWorkspaceChanged={refreshData} />}
      {activeTab === 'scenarios' && <ScenariosPage refreshKey={refreshKey} />}
      {activeTab === 'logs' && <LogsPage refreshKey={refreshKey} />}
      {activeTab === 'roi' && <RoiPage refreshKey={refreshKey} />}
    </AppShell>
  );
}
