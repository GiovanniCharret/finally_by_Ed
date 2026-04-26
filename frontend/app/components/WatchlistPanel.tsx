"use client";

import { useEffect, useRef, useState } from "react";
import { useAppState } from "../lib/AppState";
import Sparkline from "./Sparkline";

function fmtPrice(price: number | undefined | null) {
  if (price == null || Number.isNaN(price)) return "—";
  return price.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function pctChange(current: number, previous: number) {
  if (!previous || Number.isNaN(previous)) return 0;
  return ((current - previous) / previous) * 100;
}

interface RowProps {
  ticker: string;
  selected: boolean;
  onSelect: () => void;
  onRemove: () => void;
}

function WatchlistRow({ ticker, selected, onSelect, onRemove }: RowProps) {
  const { prices } = useAppState();
  const state = prices[ticker];
  const price = state?.price;
  const direction = state?.direction ?? "unchanged";
  const previous = state?.previousPrice ?? state?.price ?? 0;
  const history = state?.history ?? [];

  const [flashClass, setFlashClass] = useState("");
  const lastPriceRef = useRef<number | undefined>(price);

  useEffect(() => {
    if (price == null) return;
    const prev = lastPriceRef.current;
    if (prev != null && prev !== price) {
      const cls = price > prev ? "flash-up" : "flash-down";
      setFlashClass(cls);
      const t = setTimeout(() => setFlashClass(""), 600);
      lastPriceRef.current = price;
      return () => clearTimeout(t);
    }
    lastPriceRef.current = price;
  }, [price]);

  const change = price != null ? pctChange(price, previous) : 0;
  const changeColor =
    change > 0
      ? "text-[--color-accent-green]"
      : change < 0
      ? "text-[--color-accent-red]"
      : "text-[--color-text-secondary]";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onSelect();
      }}
      className={`group grid cursor-pointer grid-cols-[64px_1fr_80px] items-center gap-2 border-b border-[--color-border-muted]/60 px-3 py-2 text-sm transition-colors ${
        selected ? "bg-[--color-bg-panel-2]" : "hover:bg-[--color-bg-panel-2]"
      } ${flashClass}`}
      data-testid={`watchlist-row-${ticker}`}
    >
      <div className="flex flex-col">
        <span className="font-mono text-[13px] font-semibold text-[--color-text-primary]">
          {ticker}
        </span>
        <span className={`text-[11px] tabular-nums ${changeColor}`}>
          {change >= 0 ? "▲" : "▼"} {Math.abs(change).toFixed(2)}%
        </span>
      </div>
      <div className="flex flex-col items-end">
        <span
          className="font-mono text-sm tabular-nums text-[--color-text-primary]"
          data-testid={`price-${ticker}`}
        >
          {fmtPrice(price)}
        </span>
        <span className={`text-[10px] uppercase tracking-wider ${changeColor}`}>
          {direction === "up" ? "up" : direction === "down" ? "down" : "flat"}
        </span>
      </div>
      <div className="flex items-center justify-end gap-2">
        <Sparkline
          data={history.map((h) => h.value)}
          direction={direction}
          width={56}
          height={20}
        />
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="text-[--color-text-muted] opacity-0 transition-opacity hover:text-[--color-accent-red] group-hover:opacity-100"
          aria-label={`Remove ${ticker}`}
          data-testid="watchlist-remove"
        >
          ×
        </button>
      </div>
    </div>
  );
}

export default function WatchlistPanel() {
  const { watchlist, selectedTicker, setSelectedTicker, addToWatchlist, removeFromWatchlist } =
    useAppState();
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await addToWatchlist(input);
      setInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add");
    }
  }

  return (
    <aside className="flex h-full flex-col border-r border-[--color-border-muted] bg-[--color-bg-panel]">
      <div className="border-b border-[--color-border-muted] px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-[--color-text-secondary]">
          Watchlist
        </h2>
      </div>
      <div className="flex-1 overflow-y-auto">
        {watchlist.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-[--color-text-muted]">
            No tickers yet
          </div>
        ) : (
          watchlist.map((entry) => (
            <WatchlistRow
              key={entry.ticker}
              ticker={entry.ticker}
              selected={entry.ticker === selectedTicker}
              onSelect={() => setSelectedTicker(entry.ticker)}
              onRemove={() => removeFromWatchlist(entry.ticker)}
            />
          ))
        )}
      </div>
      <form onSubmit={handleAdd} className="flex flex-col gap-1 border-t border-[--color-border-muted] p-2">
        <div className="flex gap-1">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="Add ticker"
            className="flex-1 rounded border border-[--color-border-muted] bg-[--color-bg-base] px-2 py-1 font-mono text-xs text-[--color-text-primary] focus:border-[--color-accent-blue] focus:outline-none"
            maxLength={8}
            data-testid="watchlist-add-input"
          />
          <button
            type="submit"
            className="rounded border border-[--color-accent-blue] bg-[--color-accent-blue]/10 px-2 py-1 text-xs font-semibold uppercase tracking-wider text-[--color-accent-blue] hover:bg-[--color-accent-blue]/20"
            data-testid="watchlist-add-button"
          >
            Add
          </button>
        </div>
        {error ? <span className="text-[11px] text-[--color-accent-red]">{error}</span> : null}
      </form>
    </aside>
  );
}
