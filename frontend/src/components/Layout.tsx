'use client';

import { useRouter, usePathname } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';
import { ReactNode, useEffect, useState } from 'react';
import { useTheme } from '@/contexts/ThemeContext';
import {
  LayoutDashboard,
  Wallet,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  LucideIcon,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  ShieldCheck,
} from 'lucide-react';

const navigation: { name: string; href: string; icon: LucideIcon }[] = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Payments', href: '/payments', icon: Wallet },
  { name: 'Amortization', href: '/amortization', icon: FileText },
  { name: 'Reports', href: '/reports', icon: BarChart3 },
  { name: 'Audit', href: '/audit', icon: ClipboardCheck },
  { name: 'Credit Reports', href: '/credit-reports', icon: ShieldCheck },
  { name: 'Maintenance', href: '/maintenance', icon: Settings },
];

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { theme } = useTheme();
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    // Check authentication
    const authenticated = sessionStorage.getItem('authenticated');
    if (!authenticated && pathname !== '/login') {
      router.push('/login');
    }
  }, [pathname, router]);

  const handleLogout = () => {
    sessionStorage.removeItem('authenticated');
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 bg-card shadow-lg border-r border-border transition-all duration-300 ease-in-out z-20 ${
          isCollapsed ? 'w-20' : 'w-64'
        }`}
      >
        <div className="flex flex-col h-full relative">
          {/* Collapse Toggle Button */}
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="absolute -right-3 top-9 bg-card border border-border rounded-full p-1 shadow-sm hover:bg-muted text-foreground transition-colors"
          >
            {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>

          {/* Logo */}
          <div
            className={`flex items-center justify-center h-20 border-b border-border overflow-hidden transition-all ${
              isCollapsed ? 'px-2' : 'px-4'
            }`}
          >
            {!isCollapsed ? (
              <Image
                src={
                  theme === 'dark'
                    ? '/kingdom-logo-dark.png'
                    : '/kingdom-logo-light.png'
                }
                alt="Kingdom Auto Finance"
                width={180}
                height={60}
                priority
              />
            ) : (
              <div className="font-bold text-xl text-blue-600 dark:text-blue-400">
                KAF
              </div>
            )}
          </div>

          {/* Navigation */}
          <nav
            className={`flex-1 py-6 space-y-2 ${isCollapsed ? 'px-2' : 'px-4'}`}
          >
            {navigation.map((item) => {
              const isActive = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center rounded-lg transition-colors ${
                    isCollapsed ? 'justify-center p-3' : 'px-4 py-3 text-sm font-medium'
                  } ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/50 dark:text-blue-200'
                      : 'text-card-foreground hover:bg-muted'
                  }`}
                  title={isCollapsed ? item.name : ''}
                >
                  <Icon
                    className={`${
                      isCollapsed ? 'h-6 w-6' : 'mr-3 h-5 w-5'
                    } flex-shrink-0`}
                  />
                  {!isCollapsed && <span>{item.name}</span>}
                </Link>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-border">
            <button
              onClick={handleLogout}
              className={`w-full flex items-center justify-center py-2 text-sm font-medium text-red-700 bg-red-50 rounded-lg hover:bg-red-100 dark:bg-red-900/30 dark:text-red-200 dark:hover:bg-red-900/50 transition-colors ${
                isCollapsed ? 'px-2' : 'px-4'
              }`}
              title={isCollapsed ? 'Logout' : ''}
            >
              <LogOut className={`${isCollapsed ? 'h-5 w-5' : 'mr-2 h-4 w-4'}`} />
              {!isCollapsed && 'Logout'}
            </button>
            {!isCollapsed && (
              <p className="mt-4 text-xs text-center text-muted-foreground">
                v2.1.1
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div
        className={`transition-all duration-300 ease-in-out ${
          isCollapsed ? 'pl-20' : 'pl-64'
        }`}
      >
        <main className="py-8 px-8">{children}</main>
      </div>
    </div>
  );
}
