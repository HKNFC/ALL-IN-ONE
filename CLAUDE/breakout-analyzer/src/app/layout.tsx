import type { Metadata } from 'next';
import './globals.css';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { Providers } from '@/components/Providers';

export const metadata: Metadata = {
  title: 'VERDENT Breakout Analyzer',
  description: 'BIST Patlama & Breakout Analiz Sistemi',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>
        <Providers>
          <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
            <Sidebar />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <Header />
              <main style={{ flex: 1, overflowY: 'auto', position: 'relative' }}>
                <div className="grid-overlay" />
                <div style={{ position: 'relative', zIndex: 1 }}>
                  {children}
                </div>
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
