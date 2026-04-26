"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useAppState } from "../lib/AppState";

export default function PnLChart() {
  const { portfolioHistory } = useAppState();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#1a1a2e" },
        textColor: "#9ba1ad",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: "#222236" },
        horzLines: { color: "#222236" },
      },
      rightPriceScale: { borderColor: "#2a2a3e" },
      timeScale: { borderColor: "#2a2a3e", timeVisible: true, secondsVisible: false },
    });
    const series = chart.addSeries(LineSeries, {
      color: "#ecad0a",
      lineWidth: 2,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const map = new Map<number, number>();
    for (const snap of portfolioHistory) {
      const t = Math.floor(Date.parse(snap.recorded_at) / 1000);
      if (!Number.isFinite(t)) continue;
      map.set(t, snap.total_value);
    }
    const data = Array.from(map.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([time, value]) => ({ time: time as Time, value }));
    series.setData(data);
    if (data.length > 0) chartRef.current?.timeScale().fitContent();
  }, [portfolioHistory]);

  return (
    <section className="flex h-full flex-col bg-[--color-bg-panel]">
      <div className="border-b border-[--color-border-muted] px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-[--color-text-secondary]">
          Portfolio Value
        </h2>
      </div>
      <div ref={containerRef} className="flex-1" data-testid="pnl-chart" />
    </section>
  );
}
