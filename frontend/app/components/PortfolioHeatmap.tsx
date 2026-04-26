"use client";

import { useEffect, useMemo, useRef } from "react";
import { useAppState } from "../lib/AppState";
import type { Position } from "../lib/types";

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
  position: Position;
}

function squarify(
  positions: Array<{ value: number; position: Position }>,
  x: number,
  y: number,
  w: number,
  h: number,
): Rect[] {
  if (positions.length === 0) return [];
  const total = positions.reduce((s, p) => s + p.value, 0);
  if (total <= 0) return [];

  const rects: Rect[] = [];
  let cx = x;
  let cy = y;
  let cw = w;
  let ch = h;
  const items = [...positions].sort((a, b) => b.value - a.value);
  let remaining = total;

  function worst(row: typeof items, length: number): number {
    if (row.length === 0) return Infinity;
    const sum = row.reduce((s, r) => s + r.value, 0);
    let max = -Infinity;
    let min = Infinity;
    for (const r of row) {
      if (r.value > max) max = r.value;
      if (r.value < min) min = r.value;
    }
    const ratio1 = (length * length * max) / (sum * sum);
    const ratio2 = (sum * sum) / (length * length * min);
    return Math.max(ratio1, ratio2);
  }

  function layoutRow(row: typeof items, length: number, vertical: boolean) {
    const sum = row.reduce((s, r) => s + r.value, 0);
    const thick = (sum / remaining) * (vertical ? cw : ch);
    let offset = vertical ? cy : cx;
    for (const item of row) {
      const proportion = item.value / sum;
      const size = proportion * length;
      if (vertical) {
        rects.push({ x: cx, y: offset, w: thick, h: size, position: item.position });
        offset += size;
      } else {
        rects.push({ x: offset, y: cy, w: size, h: thick, position: item.position });
        offset += size;
      }
    }
    if (vertical) {
      cx += thick;
      cw -= thick;
    } else {
      cy += thick;
      ch -= thick;
    }
    remaining -= sum;
  }

  let row: typeof items = [];
  while (items.length > 0) {
    const vertical = cw < ch;
    const length = vertical ? ch : cw;
    const candidate = items[0];
    const next = [...row, candidate];
    if (row.length === 0 || worst(next, length) <= worst(row, length)) {
      row.push(items.shift()!);
    } else {
      layoutRow(row, vertical ? ch : cw, vertical);
      row = [];
    }
  }
  if (row.length > 0) {
    const vertical = cw < ch;
    layoutRow(row, vertical ? ch : cw, vertical);
  }
  return rects;
}

function colorForPnl(pct: number): string {
  // -10% → red, 0 → grey, +10% → green
  const clamped = Math.max(-10, Math.min(10, pct));
  if (clamped >= 0) {
    const t = clamped / 10;
    const r = Math.round(64 + (34 - 64) * t);
    const g = Math.round(64 + (197 - 64) * t);
    const b = Math.round(64 + (94 - 64) * t);
    return `rgb(${r}, ${g}, ${b})`;
  }
  const t = -clamped / 10;
  const r = Math.round(64 + (239 - 64) * t);
  const g = Math.round(64 + (68 - 64) * t);
  const b = Math.round(64 + (68 - 64) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

export default function PortfolioHeatmap() {
  const { portfolio } = useAppState();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const positions = useMemo(() => portfolio?.positions ?? [], [portfolio]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const dpr = window.devicePixelRatio || 1;

    function draw() {
      if (!canvas || !container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#1a1a2e";
      ctx.fillRect(0, 0, w, h);

      if (positions.length === 0) {
        ctx.fillStyle = "#5c6370";
        ctx.font = "12px ui-sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("No positions", w / 2, h / 2);
        return;
      }

      const items = positions
        .filter((p) => p.market_value > 0)
        .map((p) => ({ value: p.market_value, position: p }));
      const rects = squarify(items, 2, 2, w - 4, h - 4);

      for (const r of rects) {
        ctx.fillStyle = colorForPnl(r.position.unrealized_pnl_percent);
        ctx.fillRect(r.x, r.y, r.w, r.h);
        ctx.strokeStyle = "#0d1117";
        ctx.lineWidth = 1;
        ctx.strokeRect(r.x, r.y, r.w, r.h);
        ctx.fillStyle = "#0d1117";
        ctx.font = "bold 12px ui-monospace, monospace";
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        if (r.w > 36 && r.h > 22) {
          ctx.fillText(r.position.ticker, r.x + 6, r.y + 6);
          if (r.h > 40) {
            ctx.font = "11px ui-monospace, monospace";
            const sign = r.position.unrealized_pnl_percent >= 0 ? "+" : "";
            ctx.fillText(
              `${sign}${r.position.unrealized_pnl_percent.toFixed(2)}%`,
              r.x + 6,
              r.y + 22,
            );
          }
        }
      }
    }

    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(container);
    return () => ro.disconnect();
  }, [positions]);

  return (
    <section className="flex h-full flex-col bg-[--color-bg-panel]">
      <div className="border-b border-[--color-border-muted] px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-[--color-text-secondary]">
          Position Heatmap
        </h2>
      </div>
      <div ref={containerRef} className="relative flex-1" data-testid="heatmap">
        <canvas ref={canvasRef} className="block h-full w-full" />
      </div>
    </section>
  );
}
