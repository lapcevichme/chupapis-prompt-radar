import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Target, Activity, DollarSign, Radar, Menu, X, Moon, Sun, Database, Users, RefreshCw } from 'lucide-react';
import Dashboard from './components/Dashboard';
import Scenarios from './components/Scenarios';
import Logs from './components/Logs';
import RoiView from './components/RoiView';
import Ingestion from './components/Ingestion';
import UsersModelsView from './components/UsersModelsView';
import ProcessingBanner from './components/ProcessingBanner';
import { cn } from './lib/utils';
import { ensureAuth } from './api';

export default function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'ingestion' | 'scenarios' | 'logs' | 'roi' | 'users_models'>('dashboard');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isDark, setIsDark] = useState(true);
  const [ready, setReady] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(new Date());
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  useEffect(() => {
    ensureAuth().then(() => setReady(true));
  }, []);

  const handleManualRefresh = () => {
    setLastUpdated(new Date());
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleFetchSuccess = () => {
    setLastUpdated(new Date());
  };

  const formatLastUpdated = (date: Date | null) => {
    if (!date) return 'Updating...';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const navItems = [
    { id: 'dashboard', label: 'Overview', icon: LayoutDashboard },
    { id: 'ingestion', label: 'Ingestion & Sources', icon: Database },
    { id: 'scenarios', label: 'Scenarios', icon: Target },
    { id: 'logs', label: 'Logs & Outliers', icon: Activity },
    { id: 'users_models', label: 'Users & Models', icon: Users },
    { id: 'roi', label: 'ROI Analytics', icon: DollarSign },
  ] as const;

  if (!ready) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-accent border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="h-screen w-full overflow-hidden bg-background flex flex-col md:flex-row font-sans text-primary selection:bg-accent selection:text-white transition-colors duration-200">
      {/* Mobile Header */}
      <div className="md:hidden flex items-center justify-between p-4 bg-surface border-b border-divider shrink-0">
        <div className="flex items-center gap-2 text-primary font-bold text-xl tracking-tight">
          <Radar className="w-6 h-6 text-accent" />
          <span>PromptRadar</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setIsDark(!isDark)} className="p-2 text-secondary hover:bg-surface-hover rounded-md">
            {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
          <button onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)} className="p-2 text-secondary hover:bg-surface-hover rounded-md">
            {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Sidebar */}
      <aside className={cn(
        "fixed inset-y-0 left-0 z-50 w-64 shrink-0 bg-surface border-r border-divider transform transition-transform duration-200 ease-in-out md:relative md:translate-x-0",
        isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="h-full flex flex-col">
          <div className="p-6 hidden md:flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2 text-primary font-bold text-xl tracking-tight">
              <Radar className="w-6 h-6 text-accent" />
              <span>PromptRadar</span>
            </div>
          </div>

          <nav className="flex-1 px-4 py-2 space-y-1 overflow-y-auto">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveTab(item.id);
                    setIsMobileMenuOpen(false);
                  }}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200",
                    isActive 
                      ? "bg-accent-muted text-accent" 
                      : "text-secondary hover:bg-surface-hover hover:text-primary"
                  )}
                >
                  <Icon className={cn("w-5 h-5", isActive ? "text-accent" : "text-secondary")} />
                  {item.label}
                </button>
              );
            })}
          </nav>

          <div className="p-4 border-t border-divider flex items-center justify-between shrink-0">
            <div className="flex items-center gap-3 px-2 py-2">
              <div className="w-8 h-8 rounded-full bg-accent-muted flex items-center justify-center text-accent font-bold text-sm">
                A
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-primary">Admin</span>
                <span className="text-xs text-secondary">Workspace</span>
              </div>
            </div>
            <button onClick={() => setIsDark(!isDark)} className="hidden md:block p-2 text-secondary hover:bg-surface-hover rounded-md transition-colors">
              {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden bg-background">
        <header className="hidden md:flex h-16 shrink-0 bg-surface/80 backdrop-blur-md border-b border-divider items-center justify-between px-8 sticky top-0 z-40">
          <h1 className="text-lg font-semibold text-primary">
            {navItems.find(i => i.id === activeTab)?.label}
          </h1>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Live Polling
            </div>
            <span className="text-sm text-secondary">Last updated: {formatLastUpdated(lastUpdated)}</span>
            <button
              onClick={handleManualRefresh}
              title="Refresh data now"
              className="p-1.5 text-secondary hover:text-primary hover:bg-surface-hover rounded-md transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Global indexing/recompute progress — visible on every tab */}
        <ProcessingBanner refreshTrigger={refreshTrigger} />

        <div className="flex-1 overflow-auto p-4 md:p-8">
          <div className="max-w-7xl mx-auto pb-12">
            {activeTab === 'dashboard' && <Dashboard onFetchSuccess={handleFetchSuccess} refreshTrigger={refreshTrigger} />}
            {activeTab === 'ingestion' && <Ingestion onFetchSuccess={handleFetchSuccess} refreshTrigger={refreshTrigger} />}
            {activeTab === 'scenarios' && <Scenarios onFetchSuccess={handleFetchSuccess} refreshTrigger={refreshTrigger} />}
            {activeTab === 'logs' && <Logs onFetchSuccess={handleFetchSuccess} refreshTrigger={refreshTrigger} />}
            {activeTab === 'users_models' && <UsersModelsView onFetchSuccess={handleFetchSuccess} refreshTrigger={refreshTrigger} />}
            {activeTab === 'roi' && <RoiView onFetchSuccess={handleFetchSuccess} refreshTrigger={refreshTrigger} />}
          </div>
        </div>
      </main>

      {/* Mobile overlay */}
      {isMobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}
    </div>
  );
}
