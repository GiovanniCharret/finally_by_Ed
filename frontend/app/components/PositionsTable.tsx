"use client";

import { useAppState } from "../lib/AppState";

function fmt(n: number, digits = 2) {
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export default function PositionsTable() {
  const { portfolio, setSelectedTicker } = useAppState();
  const positions = portfolio?.positions ?? [];

  return (
    <section className="flex h-full flex-col bg-[--color-bg-panel]">
      <div className="border-b border-[--color-border-muted] px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-[--color-text-secondary]">
          Positions
        </h2>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs" data-testid="positions-table">
          <thead className="sticky top-0 bg-[--color-bg-panel] text-[--color-text-muted]">
            <tr className="border-b border-[--color-border-muted]">
              <th className="px-3 py-2 text-left font-semibold uppercase tracking-wider">Ticker</th>
              <th className="px-3 py-2 text-right font-semibold uppercase tracking-wider">Qty</th>
              <th className="px-3 py-2 text-right font-semibold uppercase tracking-wider">Avg Cost</th>
              <th className="px-3 py-2 text-right font-semibold uppercase tracking-wider">Price</th>
              <th className="px-3 py-2 text-right font-semibold uppercase tracking-wider">Mkt Value</th>
              <th className="px-3 py-2 text-right font-semibold uppercase tracking-wider">P&amp;L</th>
              <th className="px-3 py-2 text-right font-semibold uppercase tracking-wider">P&amp;L %</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {positions.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-[--color-text-muted]">
                  No open positions. Place a buy order to start.
                </td>
              </tr>
            ) : (
              positions.map((p) => {
                const positive = p.unrealized_pnl >= 0;
                const colorCls = positive
                  ? "text-[--color-accent-green]"
                  : "text-[--color-accent-red]";
                return (
                  <tr
                    key={p.ticker}
                    className="cursor-pointer border-b border-[--color-border-muted]/50 hover:bg-[--color-bg-panel-2]"
                    onClick={() => setSelectedTicker(p.ticker)}
                  >
                    <td className="px-3 py-1.5 font-semibold text-[--color-text-primary]">{p.ticker}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.quantity, 0)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.avg_cost)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.current_price)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(p.market_value)}</td>
                    <td className={`px-3 py-1.5 text-right tabular-nums ${colorCls}`}>
                      {positive ? "+" : ""}
                      {fmt(p.unrealized_pnl)}
                    </td>
                    <td className={`px-3 py-1.5 text-right tabular-nums ${colorCls}`}>
                      {positive ? "+" : ""}
                      {fmt(p.unrealized_pnl_percent)}%
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
