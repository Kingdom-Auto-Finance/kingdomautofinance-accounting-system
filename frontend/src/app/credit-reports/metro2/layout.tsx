'use client';

import Layout from '@/components/Layout';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Upload,
  Database,
  BarChart3,
  ShieldAlert,
  FileStack,
  SendHorizonal,
  Inbox,
  CalendarClock,
  FileText,
  Code2,
  Settings,
} from 'lucide-react';

const TABS = [
  { href: '/credit-reports/metro2/upload', label: 'File Upload', Icon: Upload },
  { href: '/credit-reports/metro2/records', label: 'Records', Icon: Database },
  { href: '/credit-reports/metro2/analytics', label: 'Analytics', Icon: BarChart3 },
  { href: '/credit-reports/metro2/disputes', label: 'Disputes', Icon: ShieldAlert },
  { href: '/credit-reports/metro2/file-history', label: 'File History', Icon: FileStack },
  { href: '/credit-reports/metro2/transmissions', label: 'Transmissions', Icon: SendHorizonal },
  { href: '/credit-reports/metro2/responses', label: 'Responses', Icon: Inbox },
  { href: '/credit-reports/metro2/schedules', label: 'Schedules', Icon: CalendarClock },
  { href: '/credit-reports/metro2/files', label: 'Metro 2 Files', Icon: FileText },
  { href: '/credit-reports/metro2/developers', label: 'Developers', Icon: Code2 },
  { href: '/credit-reports/metro2/account', label: 'Account', Icon: Settings },
];

export default function Metro2Layout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <Layout>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Metro 2 Platform</h1>
          <p className="text-sm text-muted-foreground">
            Native Experian Metro 2 generation, replacing Switch Labs.
          </p>
        </div>
        <Link
          href="/credit-reports"
          className="text-sm text-muted-foreground hover:underline"
        >
          ← Back to Credit Reports
        </Link>
      </div>

      <nav className="mb-6 flex flex-wrap gap-1 border-b">
        {TABS.map(({ href, label, Icon }) => {
          const active = pathname === href || pathname?.startsWith(href + '/');
          return (
            <Link
              key={href}
              href={href}
              className={
                'flex items-center gap-2 px-3 py-2 text-sm border-b-2 -mb-px transition-colors ' +
                (active
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400 font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border')
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div>{children}</div>
    </Layout>
  );
}
