import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import { useEffect } from 'react';
import { useAppStore } from '../../stores/appStore';

export default function AppLayout() {
  const { tickPrices, isLive } = useAppStore();

  useEffect(() => {
    if (!isLive) return;
    const interval = setInterval(tickPrices, 2000);
    return () => clearInterval(interval);
  }, [isLive, tickPrices]);

  return (
    <div className="scanlines flex h-screen w-screen overflow-hidden" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-auto grid-bg">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
