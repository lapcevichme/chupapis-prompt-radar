import {useState, type ComponentType, type ReactNode} from 'react';
import {Menu, Moon, Radar, Sun, X} from 'lucide-react';
import {WorkspaceActions} from '@/features/workspace-actions/WorkspaceActions';
import type {User} from '@/entities/user/types';
import {cn} from '@/shared/lib/cn';

export interface NavItem<T extends string> {
  id: T;
  label: string;
  icon: ComponentType<{className?: string}>;
}

interface AppShellProps<T extends string> {
  activeTab: T;
  children: ReactNode;
  isDark: boolean;
  navItems: NavItem<T>[];
  user: User;
  onRefresh: () => void;
  onSelectTab: (tab: T) => void;
  onToggleTheme: () => void;
}

export function AppShell<T extends string>({
  activeTab,
  children,
  isDark,
  navItems,
  user,
  onRefresh,
  onSelectTab,
  onToggleTheme,
}: AppShellProps<T>) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const activeItem = navItems.find((item) => item.id === activeTab);

  return (
    <div className="min-h-screen bg-background flex flex-col md:flex-row font-sans text-primary selection:bg-accent selection:text-white transition-colors duration-200">
      <div className="md:hidden flex items-center justify-between p-4 bg-surface border-b border-divider">
        <div className="flex items-center gap-2 text-primary font-bold text-xl tracking-normal">
          <Radar className="w-6 h-6 text-accent" />
          <span>PromptRadar</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onToggleTheme} className="p-2 text-secondary hover:bg-surface-hover rounded-md" aria-label="Toggle theme">
            {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
          <button onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)} className="p-2 text-secondary hover:bg-surface-hover rounded-md" aria-label="Open menu">
            {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-64 bg-surface border-r border-divider transform transition-transform duration-200 ease-in-out md:relative md:translate-x-0',
          isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="h-full flex flex-col">
          <div className="p-6 hidden md:flex items-center justify-between">
            <div className="flex items-center gap-2 text-primary font-bold text-xl tracking-normal">
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
                    onSelectTab(item.id);
                    setIsMobileMenuOpen(false);
                  }}
                  className={cn(
                    'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                    isActive
                      ? 'bg-accent-muted text-accent'
                      : 'text-secondary hover:bg-surface-hover hover:text-primary',
                  )}
                >
                  <Icon className={cn('w-5 h-5', isActive ? 'text-accent' : 'text-secondary')} />
                  {item.label}
                </button>
              );
            })}
          </nav>

          <div className="p-4 border-t border-divider flex items-center justify-between">
            <div className="flex items-center gap-3 px-2 py-2 min-w-0">
              <div className="w-8 h-8 rounded-full bg-accent-muted flex items-center justify-center text-accent font-bold text-sm shrink-0">
                {user.email.slice(0, 1).toUpperCase()}
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-sm font-medium text-primary truncate">{user.email}</span>
                <span className="text-xs text-secondary">Workspace</span>
              </div>
            </div>
            <button onClick={onToggleTheme} className="hidden md:block p-2 text-secondary hover:bg-surface-hover rounded-md transition-colors" aria-label="Toggle theme">
              {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="hidden md:flex min-h-16 bg-surface/80 backdrop-blur-md border-b border-divider items-center justify-between gap-4 px-8 sticky top-0 z-40">
          <h1 className="text-lg font-semibold text-primary">{activeItem?.label}</h1>
          <WorkspaceActions onRefresh={onRefresh} />
        </header>

        <div className="md:hidden p-4 border-b border-divider bg-surface">
          <WorkspaceActions onRefresh={onRefresh} />
        </div>

        <div className="flex-1 overflow-auto p-4 md:p-8">
          <div className="max-w-7xl mx-auto">{children}</div>
        </div>
      </main>

      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}
    </div>
  );
}
