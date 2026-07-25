import {lazy, Suspense, useCallback, useEffect, useRef, useState} from 'react';
import {Activity, Database, DollarSign, LayoutDashboard, Target} from 'lucide-react';
import {promptRadarApi} from '@/shared/api/promptRadarApi';
import {ApiError} from '@/shared/api/http';
import {
  AUTO_DEMO_LOGIN,
  DEMO_EMAIL,
  DEMO_PASSWORD,
  FALLBACK_DEMO_EMAIL,
  FALLBACK_DEMO_PASSWORD,
} from '@/shared/config/env';
import type {User} from '@/entities/user/types';
import type {WorkspaceFilters as WorkspaceFilterValues} from '@/entities/workspace/types';
import {DatasetSwitcher} from '@/features/dataset-switcher/DatasetSwitcher';
import {WorkspaceFilters} from '@/features/workspace-filters/WorkspaceFilters';
import LoginPage from '@/pages/auth/LoginPage';
import {AppShell, type NavItem} from '@/widgets/app-shell/AppShell';
import {LoadingState} from '@/widgets/data-state/DataState';

type TabId = 'dashboard' | 'sources' | 'scenarios' | 'logs' | 'roi';

const DashboardPage = lazy(() => import('@/pages/dashboard/DashboardPage'));
const LogsPage = lazy(() => import('@/pages/logs/LogsPage'));
const RoiPage = lazy(() => import('@/pages/roi/RoiPage'));
const ScenariosPage = lazy(() => import('@/pages/scenarios/ScenariosPage'));
const SourcesPage = lazy(() => import('@/pages/sources/SourcesPage'));

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
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [filters, setFilters] = useState<WorkspaceFilterValues>({});
  const autoLoginAttempted = useRef(false);

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

        if (!AUTO_DEMO_LOGIN || autoLoginAttempted.current) {
          setUser(null);
          return;
        }

        autoLoginAttempted.current = true;
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

  const handleLogin = useCallback(async (email: string, password: string) => {
    setIsAuthenticating(true);
    setAuthError(null);
    autoLoginAttempted.current = true;
    try {
      const response = await promptRadarApi.login({email, password});
      setUser(response.user);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Authorization failed');
    } finally {
      setIsAuthenticating(false);
    }
  }, []);

  const handleLogout = useCallback(async () => {
    setIsLoggingOut(true);
    setAuthError(null);
    autoLoginAttempted.current = true;
    try {
      await promptRadarApi.logout();
      setUser(null);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Logout failed');
      setUser(null);
    } finally {
      setIsLoggingOut(false);
    }
  }, []);

  useEffect(() => {
    void bootstrapAuth();
  }, [bootstrapAuth]);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
  }, [isDark]);

  useEffect(() => {
    if (!user) {
      return;
    }
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        refreshData();
      }
    }, 15_000);
    return () => window.clearInterval(intervalId);
  }, [refreshData, user]);

  if (isBootstrapping) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <LoadingState title="Connecting to backend" />
      </div>
    );
  }

  if (!user) {
    return (
      <LoginPage
        error={authError}
        initialEmail={AUTO_DEMO_LOGIN ? FALLBACK_DEMO_EMAIL : ''}
        initialPassword={AUTO_DEMO_LOGIN ? FALLBACK_DEMO_PASSWORD : ''}
        isPending={isAuthenticating}
        onLogin={handleLogin}
      />
    );
  }

  return (
    <AppShell<TabId>
      activeTab={activeTab}
      isDark={isDark}
      navItems={navItems}
      secondaryToolbar={
        activeTab === 'sources' || activeTab === 'scenarios' ? undefined : (
          <>
            <DatasetSwitcher filters={filters} onChange={setFilters} refreshKey={refreshKey} />
            <WorkspaceFilters filters={filters} onChange={setFilters} />
          </>
        )
      }
      user={user}
      isLoggingOut={isLoggingOut}
      onLogout={() => void handleLogout()}
      onRefresh={refreshData}
      onSelectTab={(tab) => setActiveTab(tab)}
      onToggleTheme={() => setIsDark((value) => !value)}
    >
      <Suspense fallback={<LoadingState title="Loading workspace" />}>
        {activeTab === 'dashboard' && (
          <DashboardPage filters={filters} onOpenSources={() => setActiveTab('sources')} refreshKey={refreshKey} />
        )}
        {activeTab === 'sources' && <SourcesPage refreshKey={refreshKey} onWorkspaceChanged={refreshData} />}
        {activeTab === 'scenarios' && (
          <ScenariosPage
            filters={filters}
            refreshKey={refreshKey}
            workspaceFiltersControl={(
              <div className="flex flex-wrap items-center gap-3">
                <DatasetSwitcher filters={filters} onChange={setFilters} refreshKey={refreshKey} />
                <WorkspaceFilters filters={filters} onChange={setFilters} />
              </div>
            )}
          />
        )}
        {activeTab === 'logs' && <LogsPage filters={filters} refreshKey={refreshKey} />}
        {activeTab === 'roi' && <RoiPage filters={filters} refreshKey={refreshKey} />}
      </Suspense>
    </AppShell>
  );
}
