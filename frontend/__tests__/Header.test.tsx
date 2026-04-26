import { render, screen } from "@testing-library/react";
import Header from "../app/components/Header";
import * as AppState from "../app/lib/AppState";

jest.mock("../app/lib/AppState");

const mockedUseAppState = AppState.useAppState as jest.MockedFunction<typeof AppState.useAppState>;

function buildState(overrides: Partial<ReturnType<typeof AppState.useAppState>> = {}) {
  return {
    prices: {},
    watchlist: [],
    portfolio: {
      cash_balance: 8420.5,
      total_value: 10120.75,
      unrealized_pnl: 120.75,
      positions: [],
    },
    portfolioHistory: [],
    selectedTicker: "AAPL",
    connectionStatus: "connected" as const,
    chatMessages: [],
    chatLoading: false,
    chatPanelOpen: true,
    setSelectedTicker: jest.fn(),
    refreshWatchlist: jest.fn(),
    refreshPortfolio: jest.fn(),
    refreshPortfolioHistory: jest.fn(),
    addToWatchlist: jest.fn(),
    removeFromWatchlist: jest.fn(),
    sendChatMessage: jest.fn(),
    toggleChatPanel: jest.fn(),
    ...overrides,
  };
}

describe("Header", () => {
  it("renders total value, cash balance, and a green status dot when connected", () => {
    mockedUseAppState.mockReturnValue(buildState());

    render(<Header />);

    expect(screen.getByTestId("total-value")).toHaveTextContent("$10,120.75");
    expect(screen.getByTestId("cash-balance")).toHaveTextContent("$8,420.50");
    expect(screen.getByTestId("pnl")).toHaveTextContent("+$120.75");
    const dot = screen.getByTestId("connection-dot");
    expect(dot.className).toContain("bg-[--color-accent-green]");
  });

  it("shows the disconnected status with red dot", () => {
    mockedUseAppState.mockReturnValue(buildState({ connectionStatus: "disconnected" }));
    render(<Header />);
    const dot = screen.getByTestId("connection-dot");
    expect(dot.className).toContain("bg-[--color-accent-red]");
  });

  it("renders an em dash when portfolio is null", () => {
    mockedUseAppState.mockReturnValue(buildState({ portfolio: null }));
    render(<Header />);
    expect(screen.getByTestId("total-value")).toHaveTextContent("—");
  });
});
