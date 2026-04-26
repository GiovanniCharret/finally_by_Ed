import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import TradeBar from "../app/components/TradeBar";
import * as AppState from "../app/lib/AppState";

jest.mock("../app/lib/AppState");
const mockedUseAppState = AppState.useAppState as jest.MockedFunction<typeof AppState.useAppState>;

const refreshPortfolio = jest.fn();
const refreshPortfolioHistory = jest.fn();

const baseState = {
  selectedTicker: "AAPL",
  refreshPortfolio,
  refreshPortfolioHistory,
  prices: {},
  watchlist: [],
  portfolio: null,
  portfolioHistory: [],
  connectionStatus: "connected" as const,
  chatMessages: [],
  chatLoading: false,
  chatPanelOpen: true,
  setSelectedTicker: jest.fn(),
  refreshWatchlist: jest.fn(),
  addToWatchlist: jest.fn(),
  removeFromWatchlist: jest.fn(),
  sendChatMessage: jest.fn(),
  toggleChatPanel: jest.fn(),
};

describe("TradeBar", () => {
  beforeEach(() => {
    mockedUseAppState.mockReturnValue(baseState);
    refreshPortfolio.mockReset();
    refreshPortfolioHistory.mockReset();
    (global.fetch as jest.Mock | undefined) = jest.fn().mockResolvedValue({
      ok: true,
      text: async () =>
        JSON.stringify({
          trade_id: "abc",
          ticker: "AAPL",
          side: "buy",
          quantity: 5,
          price: 194.25,
          executed_at: "2026-04-22T12:00:00Z",
        }),
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("submits a buy via /api/portfolio/trade with the typed quantity and ticker", async () => {
    render(<TradeBar />);
    fireEvent.change(screen.getByTestId("trade-quantity"), { target: { value: "5" } });
    fireEvent.click(screen.getByTestId("trade-buy"));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });
    const call = (global.fetch as jest.Mock).mock.calls[0];
    expect(call[0]).toBe("/api/portfolio/trade");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ ticker: "AAPL", quantity: 5, side: "buy" });

    await waitFor(() => {
      expect(screen.getByTestId("trade-message")).toHaveTextContent("Bought 5 AAPL @ $194.25");
    });
    expect(refreshPortfolio).toHaveBeenCalled();
  });

  it("rejects an empty quantity without calling the API", async () => {
    render(<TradeBar />);
    fireEvent.change(screen.getByTestId("trade-quantity"), { target: { value: "" } });
    fireEvent.click(screen.getByTestId("trade-buy"));
    await waitFor(() => {
      expect(screen.getByTestId("trade-message")).toHaveTextContent(
        "Quantity must be a positive integer",
      );
    });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("shows a server error message when the trade is rejected", async () => {
    (global.fetch as jest.Mock) = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      text: async () =>
        JSON.stringify({
          error: { code: "insufficient_cash", message: "Need $971.25, have $420.00" },
        }),
    });
    render(<TradeBar />);
    fireEvent.click(screen.getByTestId("trade-buy"));
    await waitFor(() => {
      expect(screen.getByTestId("trade-message")).toHaveTextContent(
        "Need $971.25, have $420.00",
      );
    });
  });

  it("rejects a zero quantity without calling the API", async () => {
    render(<TradeBar />);
    fireEvent.change(screen.getByTestId("trade-quantity"), { target: { value: "0" } });
    fireEvent.click(screen.getByTestId("trade-buy"));
    await waitFor(() => {
      expect(screen.getByTestId("trade-message")).toHaveTextContent(
        "Quantity must be a positive integer",
      );
    });
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
