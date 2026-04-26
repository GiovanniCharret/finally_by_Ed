"use client";

import { useAppState } from "../lib/AppState";

const STATUS_COLORS = {
  connected: "bg-[--color-accent-green]",
  connecting: "bg-[--color-accent-yellow]",
  disconnected: "bg-[--color-accent-red]",
};

const STATUS_LABEL = {
  connected: "Live",
  connecting: "Connecting…",
  disconnected: "Disconnected",
};

function fmt(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
}

export default function Header() {
  const { portfolio, connectionStatus, toggleChatPanel, chatPanelOpen } = useAppState();
  const totalValue = portfolio?.total_value ?? null;
  const cash = portfolio?.cash_balance ?? null;
  const pnl = portfolio?.unrealized_pnl ?? 0;
  const pnlPositive = pnl >= 0;

  return (
    <header
      className="flex items-center justify-between border-b border-[--color-border-muted] bg-[--color-bg-panel] px-5 py-3"
      data-testid="header"
    >
      <div className="flex items-center gap-3">
        <span className="text-xl font-bold tracking-wider text-[--color-accent-yellow]">
          FinAlly
        </span>
        <span className="hidden text-xs uppercase tracking-widest text-[--color-text-muted] sm:inline">
          Trading Workstation
        </span>
      </div>
      <div className="flex items-center gap-6">
        <div className="flex flex-col items-end leading-tight">
          <span className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
            Total Value
          </span>
          <span
            className="text-lg font-semibold tabular-nums text-[--color-accent-blue]"
            data-testid="total-value"
          >
            {fmt(totalValue)}
          </span>
        </div>
        <div className="flex flex-col items-end leading-tight">
          <span className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
            Cash
          </span>
          <span
            className="text-lg font-semibold tabular-nums text-[--color-text-primary]"
            data-testid="cash-balance"
          >
            {fmt(cash)}
          </span>
        </div>
        <div className="flex flex-col items-end leading-tight">
          <span className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
            Unrealized P&amp;L
          </span>
          <span
            className={`text-lg font-semibold tabular-nums ${
              pnlPositive ? "text-[--color-accent-green]" : "text-[--color-accent-red]"
            }`}
            data-testid="pnl"
          >
            {pnl >= 0 ? "+" : ""}
            {fmt(pnl)}
          </span>
        </div>
        <div className="flex items-center gap-2 rounded-md border border-[--color-border-muted] px-3 py-1.5">
          <span
            data-testid="connection-dot"
            className={`inline-block h-2 w-2 rounded-full ${STATUS_COLORS[connectionStatus]}`}
            aria-label={STATUS_LABEL[connectionStatus]}
          />
          <span className="text-xs uppercase tracking-wider text-[--color-text-secondary]">
            {STATUS_LABEL[connectionStatus]}
          </span>
        </div>
        <button
          type="button"
          onClick={toggleChatPanel}
          className="rounded-md border border-[--color-border-muted] px-3 py-1.5 text-xs uppercase tracking-wider text-[--color-text-secondary] hover:border-[--color-accent-blue] hover:text-[--color-accent-blue]"
        >
          {chatPanelOpen ? "Hide Chat" : "Show Chat"}
        </button>
      </div>
    </header>
  );
}
