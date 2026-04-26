"use client";

import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useAppState } from "../lib/AppState";

export default function MainChart() {
  const { selectedTicker, prices } = useAppState();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#0d1117" },
        textColor: "#9ba1ad",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: "#1a1a2e" },
        horzLines: { color: "#1a1a2e" },
      },
      rightPriceScale: { borderColor: "#2a2a3e" },
      timeScale: { borderColor: "#2a2a3e", timeVisible: true, secondsVisible: true },
      crosshair: { mode: 1 },
    });
    const series = chart.addSeries(AreaSeries, {
      lineColor: "#209dd7",
      topColor: "rgba(32, 157, 215, 0.35)",
      bottomColor: "rgba(32, 157, 215, 0.02)",
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
    const state = prices[selectedTicker];
    const history = state?.history ?? [];
    if (history.length === 0) {
      series.setData([]);
      return;
    }
    // dedupe by time, lightweight-charts requires strictly ascending unique times
    const map = new Map<number, number>();
    for (const point of history) {
      map.set(Math.floor(point.time), point.value);
    }
    const data = Array.from(map.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([time, value]) => ({ time: time as Time, value }));
    series.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [selectedTicker, prices]);

  const state = prices[selectedTicker];
  const price = state?.price;
  const direction = state?.direction ?? "unchanged";

  return (
    <section className="flex h-full flex-col bg-[--color-bg-panel]">
      <div className="flex items-center justify-between border-b border-[--color-border-muted] px-4 py-2">
        <div className="flex items-baseline gap-3">
          <h2 className="font-mono text-lg font-bold tracking-wide text-[--color-text-primary]">
            {selectedTicker}
          </h2>
          <span
            className={`font-mono text-base tabular-nums ${
              direction === "up"
                ? "text-[--color-accent-green]"
                : direction === "down"
                ? "text-[--color-accent-red]"
                : "text-[--color-text-secondary]"
            }`}
          >
            {price != null ? price.toFixed(2) : "—"}
          </span>
        </div>
        <span className="text-xs uppercase tracking-widest text-[--color-text-muted]">
          Live
        </span>
      </div>
      <div ref={containerRef} className="flex-1" data-testid="main-chart" />
    </section>
  );
}
