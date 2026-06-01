import React, { ReactNode } from 'react';

interface SidebarLayoutProps {
  sidebar: ReactNode;
  children: ReactNode;
}

export function SidebarLayout({ sidebar, children }: SidebarLayoutProps) {
  return (
    <div className="flex flex-1 gap-6 h-full">
      <aside className="w-80 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 overflow-y-auto flex-shrink-0">
        {sidebar}
      </aside>
      <main className="flex-1 overflow-y-auto pr-6">
        {children}
      </main>
    </div>
  );
}
