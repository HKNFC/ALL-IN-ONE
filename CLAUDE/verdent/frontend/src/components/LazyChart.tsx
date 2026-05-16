/**
 * LazyChart — lazy-loads a chart component only when it scrolls into view.
 * Reduces initial bundle parse time and avoids off-screen WebGL/canvas work.
 */
import { Suspense, lazy, useRef, useState, useEffect, type ComponentType } from 'react';
import { Loader2 } from 'lucide-react';

interface Props<P extends object> {
  /** Async import function: () => import('./SomeChart') */
  loader:  () => Promise<{ default: ComponentType<P> }>;
  props:   P;
  height?: number;
  label?:  string;
}

export function LazyChart<P extends object>({ loader, props, height = 300, label }: Props<P>) {
  const containerRef  = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  // Observe intersection — only render chart when in viewport
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); observer.disconnect(); } },
      { rootMargin: '200px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Lazily create the component only once per `loader` reference
  const LazyComponent = lazy(loader);

  return (
    <div ref={containerRef} style={{ minHeight: height }} className="w-full">
      {visible ? (
        <Suspense fallback={<ChartSkeleton height={height} label={label} />}>
          <LazyComponent {...(props as P & JSX.IntrinsicAttributes)} />
        </Suspense>
      ) : (
        <ChartSkeleton height={height} label={label} />
      )}
    </div>
  );
}

function ChartSkeleton({ height, label }: { height: number; label?: string }) {
  return (
    <div
      style={{ height }}
      className="w-full flex flex-col items-center justify-center gap-2
                 bg-gray-900/50 rounded-xl border border-gray-800 animate-pulse"
    >
      <Loader2 size={20} className="text-gray-600 animate-spin" />
      {label && <span className="text-xs text-gray-600">{label}</span>}
    </div>
  );
}
