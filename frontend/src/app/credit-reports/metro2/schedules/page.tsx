'use client';

import { CalendarClock } from 'lucide-react';

export default function SchedulesPage() {
  return (
    <div className="border rounded bg-card p-8 text-center">
      <CalendarClock className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
      <div className="font-medium">Automated scheduling — coming soon</div>
      <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
        For now, generate Metro 2 files manually from the{' '}
        <span className="font-medium">Metro 2 Files</span> tab. Automated
        monthly runs will land in v2.
      </p>
    </div>
  );
}
