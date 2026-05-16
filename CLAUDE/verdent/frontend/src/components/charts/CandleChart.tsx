import { useEffect, useRef } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
} from 'lightweight-charts';
import type { OHLCVData } from '../../types';

interface CandleChartProps {
  data: OHLCVData[];
  height?: number;
  showVolume?: boolean;
  symbol?: string;
}

export default function CandleChart({ data, height = 340, showVolume = true, symbol = '' }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: showVolume ? height : height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#828aa5',
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: 'rgba(30,34,52,0.8)' },
        horzLines: { color: 'rgba(30,34,52,0.8)' },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: 'rgba(0,208,132,0.4)', style: 0 },
        horzLine: { color: 'rgba(0,208,132,0.4)', style: 0 },
      },
      rightPriceScale: {
        borderColor: '#1e2234',
        textColor: '#828aa5',
      },
      timeScale: {
        borderColor: '#1e2234',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:   '#00D084',
      downColor: '#FF4757',
      borderUpColor:   '#00D084',
      borderDownColor: '#FF4757',
      wickUpColor:     '#00D084',
      wickDownColor:   '#FF4757',
    });

    candleSeries.setData(data.map(d => ({
      time: d.time as any,
      open: d.open, high: d.high, low: d.low, close: d.close,
    })));

    if (showVolume) {
      const volSeries = chart.addSeries(HistogramSeries, {
        color: '#26a69a',
        priceFormat: { type: 'volume' },
        priceScaleId: 'vol',
      });
      chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      volSeries.setData(data.map(d => ({
        time: d.time as any,
        value: d.volume,
        color: d.close >= d.open ? 'rgba(0,208,132,0.25)' : 'rgba(255,71,87,0.25)',
      })));
    }

    // MA 20
    const ma20Data: { time: any; value: number }[] = [];
    for (let i = 19; i < data.length; i++) {
      const avg = data.slice(i - 19, i + 1).reduce((s, d) => s + d.close, 0) / 20;
      ma20Data.push({ time: data[i].time as any, value: +avg.toFixed(2) });
    }
    const ma20 = chart.addSeries(LineSeries, { color: 'rgba(255,199,0,0.7)', lineWidth: 1, priceLineVisible: false });
    ma20.setData(ma20Data);

    // MA 50
    const ma50Data: { time: any; value: number }[] = [];
    for (let i = 49; i < data.length; i++) {
      const avg = data.slice(i - 49, i + 1).reduce((s, d) => s + d.close, 0) / 50;
      ma50Data.push({ time: data[i].time as any, value: +avg.toFixed(2) });
    }
    const ma50 = chart.addSeries(LineSeries, { color: 'rgba(64,156,255,0.7)', lineWidth: 1, priceLineVisible: false });
    ma50.setData(ma50Data);

    chart.timeScale().fitContent();

    // Resize observer
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [data, height, showVolume]);

  return (
    <div style={{ position: 'relative' }}>
      {symbol && (
        <div style={{
          position: 'absolute', top: 10, left: 12, zIndex: 10,
          color: 'var(--text)', fontSize: 12, fontWeight: 700,
          background: 'rgba(8,9,14,0.7)', padding: '2px 8px', borderRadius: 4,
        }}>
          {symbol}
        </div>
      )}
      <div style={{ position: 'absolute', top: 10, right: 12, zIndex: 10, display: 'flex', gap: 12, fontSize: 10 }}>
        <span style={{ color: 'rgba(255,199,0,0.9)' }}>— MA20</span>
        <span style={{ color: 'rgba(64,156,255,0.9)' }}>— MA50</span>
      </div>
      <div ref={containerRef} />
    </div>
  );
}
