'use client';

import { useRouter, usePathname } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';
import { ReactNode, useEffect } from 'react';
import { useTheme } from '@/contexts/ThemeContext';
import {
  LayoutDashboard,
  Wallet,
  FileText,
  BarChart3,
  Settings,
  LogOut,
  LucideIcon,
} from 'lucide-react';

const navigation: { name: string; href: string; icon: LucideIcon }[] = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Payments', href: '/payments', icon: Wallet },
  { name: 'Amortization', href: '/amortization', icon: FileText },
  { name: 'Reports', href: '/reports', icon: BarChart3 },
  { name: 'Maintenance', href: '/maintenance', icon: Settings },
];

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { theme } = useTheme();

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
    <div className="min-h-screen bg-background">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-card shadow-lg border-r border-border">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center justify-center h-20 border-b border-border">
            <Image
              src={theme === 'dark' ? '/kingdom-logo-dark.png' : '/kingdom-logo-light.png'}
              alt="Kingdom Auto Finance"
              width={180}
              height={60}
              priority
            />
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 py-6 space-y-2">
            {navigation.map((item) => {
              const isActive = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-200'
                      : 'text-card-foreground hover:bg-muted'
                  }`}
                >
                  <Icon className="mr-3 h-5 w-5" />
                  {item.name}
                </Link>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-border">
            <button
              onClick={handleLogout}
              className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium text-red-700 bg-red-50 rounded-lg hover:bg-red-100 dark:bg-red-950 dark:text-red-200 dark:hover:bg-red-900 transition-colors"
            >
              <LogOut className="mr-2 h-4 w-4" />
              Logout
            </button>
            <p className="mt-4 text-xs text-center text-muted-foreground">
              v2.1.1
            </p>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="pl-64">
        <main className="py-8 px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
