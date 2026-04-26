import { act, render, screen } from "@testing-library/react";
import WatchlistPanel from "../app/components/WatchlistPanel";
import * as AppState from "../app/lib/AppState";
import type { PriceState } from "../app/lib/types";

jest.mock("../app/lib/AppState");

const mockedUseAppState = AppState.useAppState as jest.MockedFunction<typeof AppState.useAppState>;

function makePrice(ticker: string, price: number, prev: number, history: number[]): PriceState {
  return {
    ticker,
    price,
    previousPrice: prev,
    direction: price > prev ? "up" : price < prev ? "down" : "unchanged",
    history: history.map((v, i) => ({ time: i, value: v })),
  };
}

const baseState = {
  watchlist: [
    { ticker: "AAPL", price: 200, previous_price: 199, direction: "up" as const },
    { ticker: "TSLA", price: 250, previous_price: 251, direction: "down" as const },
  ],
  selectedTicker: "AAPL",
  setSelectedTicker: jest.fn(),
  addToWatchlist: jest.fn(),
  removeFromWatchlist: jest.fn(),
  prices: {
    AAPL: makePrice("AAPL", 200.5, 199.0, [199, 199.5, 200, 200.5]),
    TSLA: makePrice("TSLA", 248.0, 251.0, [251, 250, 249, 248]),
  } as Record<string, PriceState>,
  portfolio: null,
  portfolioHistory: [],
  connectionStatus: "connected" as const,
  chatMessages: [],
  chatLoading: false,
  chatPanelOpen: true,
  refreshWatchlist: jest.fn(),
  refreshPortfolio: jest.fn(),
  refreshPortfolioHistory: jest.fn(),
  sendChatMessage: jest.fn(),
  toggleChatPanel: jest.fn(),
};

describe("WatchlistPanel", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });
  afterEach(() => {
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  it("renders one row per watchlist ticker with current price", () => {
    mockedUseAppState.mockReturnValue(baseState);
    render(<WatchlistPanel />);
    expect(screen.getByTestId("watchlist-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-row-TSLA")).toBeInTheDocument();
    expect(screen.getByTestId("price-AAPL")).toHaveTextContent("200.50");
    expect(screen.getByTestId("price-TSLA")).toHaveTextContent("248.00");
  });

  it("applies a flash-up class when an updated price is higher than the previous", () => {
    mockedUseAppState.mockReturnValue(baseState);
    const { rerender } = render(<WatchlistPanel />);

    const updated = {
      ...baseState,
      prices: {
        ...baseState.prices,
        AAPL: makePrice("AAPL", 201.25, 200.5, [199, 200, 200.5, 201.25]),
      },
    };
    mockedUseAppState.mockReturnValue(updated);
    rerender(<WatchlistPanel />);

    const row = screen.getByTestId("watchlist-row-AAPL");
    expect(row.className).toContain("flash-up");
  });

  it("applies a flash-down class on a downward tick", () => {
    mockedUseAppState.mockReturnValue(baseState);
    const { rerender } = render(<WatchlistPanel />);

    const updated = {
      ...baseState,
      prices: {
        ...baseState.prices,
        AAPL: makePrice("AAPL", 199.0, 200.5, [199, 200, 200.5, 199]),
      },
    };
    mockedUseAppState.mockReturnValue(updated);
    rerender(<WatchlistPanel />);

    const row = screen.getByTestId("watchlist-row-AAPL");
    expect(row.className).toContain("flash-down");
  });

  it("clears the flash class after the animation timeout", () => {
    mockedUseAppState.mockReturnValue(baseState);
    const { rerender } = render(<WatchlistPanel />);

    mockedUseAppState.mockReturnValue({
      ...baseState,
      prices: {
        ...baseState.prices,
        AAPL: makePrice("AAPL", 201.0, 200.5, [199, 200, 200.5, 201]),
      },
    });
    rerender(<WatchlistPanel />);
    expect(screen.getByTestId("watchlist-row-AAPL").className).toContain("flash-up");

    act(() => {
      jest.advanceTimersByTime(700);
    });
    expect(screen.getByTestId("watchlist-row-AAPL").className).not.toContain("flash-up");
  });
});
