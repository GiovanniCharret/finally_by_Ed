import { render, screen } from "@testing-library/react";
import ChatPanel from "../app/components/ChatPanel";
import * as AppState from "../app/lib/AppState";
import type { ChatMessage } from "../app/lib/types";

jest.mock("../app/lib/AppState");
const mockedUseAppState = AppState.useAppState as jest.MockedFunction<typeof AppState.useAppState>;

const baseState = (overrides: Partial<ReturnType<typeof AppState.useAppState>> = {}) => ({
  prices: {},
  watchlist: [],
  portfolio: null,
  portfolioHistory: [],
  selectedTicker: "AAPL",
  connectionStatus: "connected" as const,
  chatMessages: [] as ChatMessage[],
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
});

describe("ChatPanel", () => {
  it("renders nothing when the panel is collapsed", () => {
    mockedUseAppState.mockReturnValue(baseState({ chatPanelOpen: false }));
    const { container } = render(<ChatPanel />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the loading spinner while a chat request is in flight", () => {
    mockedUseAppState.mockReturnValue(baseState({ chatLoading: true }));
    render(<ChatPanel />);
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
  });

  it("renders an assistant message and inline action results", () => {
    mockedUseAppState.mockReturnValue(
      baseState({
        chatMessages: [
          { role: "user", content: "Buy 2 AAPL" },
          {
            role: "assistant",
            content: "Done — bought 2 AAPL.",
            action_results: [
              { type: "trade", ticker: "AAPL", status: "executed", side: "buy", quantity: 2 },
            ],
          },
        ],
      }),
    );
    render(<ChatPanel />);
    expect(screen.getByTestId("chat-msg-user")).toHaveTextContent("Buy 2 AAPL");
    expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent("Done — bought 2 AAPL.");
    expect(screen.getByTestId("chat-msg-assistant")).toHaveTextContent("Bought 2 AAPL");
  });

  it("disables the send button while loading", () => {
    mockedUseAppState.mockReturnValue(baseState({ chatLoading: true }));
    render(<ChatPanel />);
    const send = screen.getByTestId("chat-send") as HTMLButtonElement;
    expect(send.disabled).toBe(true);
  });
});
