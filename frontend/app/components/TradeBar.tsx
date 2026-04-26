"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAppState } from "../lib/AppState";

type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

export default function TradeBar() {
  const { selectedTicker, refreshPortfolio, refreshPortfolioHistory } = useAppState();
  const [ticker, setTicker] = useState(selectedTicker);
  const [quantity, setQuantity] = useState<string>("1");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  useEffect(() => {
    setTicker(selectedTicker);
  }, [selectedTicker]);

  async function submit(side: "buy" | "sell") {
    const qty = parseInt(quantity, 10);
    if (!ticker.trim()) {
      setStatus({ kind: "error", message: "Ticker is required" });
      return;
    }
    if (!Number.isInteger(qty) || qty < 1) {
      setStatus({ kind: "error", message: "Quantity must be a positive integer" });
      return;
    }
    setStatus({ kind: "submitting" });
    try {
      const res = await api.trade({ ticker: ticker.trim().toUpperCase(), quantity: qty, side });
      setStatus({
        kind: "success",
        message: `${side === "buy" ? "Bought" : "Sold"} ${res.quantity} ${res.ticker} @ $${res.price.toFixed(2)}`,
      });
      await Promise.all([refreshPortfolio(), refreshPortfolioHistory()]);
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof Error ? err.message : "Trade failed",
      });
    }
  }

  const submitting = status.kind === "submitting";
  const message =
    status.kind === "success" || status.kind === "error" ? status.message : null;
  const messageColor =
    status.kind === "success" ? "text-[--color-accent-green]" : "text-[--color-accent-red]";

  return (
    <section
      className="flex flex-wrap items-center gap-3 border-t border-[--color-border-muted] bg-[--color-bg-panel] px-4 py-3"
      data-testid="trade-bar"
    >
      <div className="flex flex-col">
        <label className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
          Ticker
        </label>
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          className="w-24 rounded border border-[--color-border-muted] bg-[--color-bg-base] px-2 py-1 font-mono text-sm text-[--color-text-primary] focus:border-[--color-accent-blue] focus:outline-none"
          maxLength={8}
          data-testid="trade-ticker"
        />
      </div>
      <div className="flex flex-col">
        <label className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
          Quantity
        </label>
        <input
          type="number"
          min={1}
          step={1}
          value={quantity}
          onChange={(e) => {
            // strip non-digits aggressively for integer-only input
            const cleaned = e.target.value.replace(/[^0-9]/g, "");
            setQuantity(cleaned);
          }}
          className="w-24 rounded border border-[--color-border-muted] bg-[--color-bg-base] px-2 py-1 font-mono text-sm text-[--color-text-primary] focus:border-[--color-accent-blue] focus:outline-none"
          data-testid="trade-quantity"
        />
      </div>
      <button
        type="button"
        disabled={submitting}
        onClick={() => submit("buy")}
        className="rounded-md bg-[--color-accent-purple] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        data-testid="trade-buy"
      >
        {submitting ? "…" : "Buy"}
      </button>
      <button
        type="button"
        disabled={submitting}
        onClick={() => submit("sell")}
        className="rounded-md bg-[--color-accent-red] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        data-testid="trade-sell"
      >
        {submitting ? "…" : "Sell"}
      </button>
      {message ? (
        <span className={`text-xs ${messageColor}`} data-testid="trade-message">
          {message}
        </span>
      ) : null}
    </section>
  );
}
