"use client";

import ChatPanel from "./components/ChatPanel";
import Header from "./components/Header";
import MainChart from "./components/MainChart";
import PnLChart from "./components/PnLChart";
import PortfolioHeatmap from "./components/PortfolioHeatmap";
import PositionsTable from "./components/PositionsTable";
import TradeBar from "./components/TradeBar";
import WatchlistPanel from "./components/WatchlistPanel";
import { AppStateProvider } from "./lib/AppState";

export default function Home() {
  return (
    <AppStateProvider>
      <div className="flex h-screen w-screen flex-col bg-[--color-bg-base] text-[--color-text-primary]">
        <Header />
        <div className="flex flex-1 overflow-hidden">
          <div className="w-[280px] flex-shrink-0">
            <WatchlistPanel />
          </div>
          <main className="flex flex-1 flex-col overflow-hidden">
            <div className="grid flex-1 grid-cols-1 grid-rows-[1fr_1fr] gap-px overflow-hidden bg-[--color-border-muted] lg:grid-cols-2 lg:grid-rows-[1.4fr_1fr]">
              <div className="lg:col-span-2">
                <MainChart />
              </div>
              <PortfolioHeatmap />
              <PnLChart />
            </div>
            <div className="h-[210px] flex-shrink-0 border-t border-[--color-border-muted]">
              <PositionsTable />
            </div>
            <TradeBar />
          </main>
          <ChatPanel />
        </div>
      </div>
    </AppStateProvider>
  );
}
