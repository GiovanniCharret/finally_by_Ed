"use client";

import { useEffect, useRef, useState } from "react";
import { useAppState } from "../lib/AppState";
import type { ActionResult } from "../lib/types";

function ActionBadge({ result }: { result: ActionResult }) {
  const success = result.status === "executed";
  const icon = success ? "✓" : "✗";
  const color = success
    ? "text-[--color-accent-green]"
    : "text-[--color-accent-red]";
  let label: string;
  if (result.type === "trade") {
    const verb = result.side === "buy" ? "Bought" : "Sold";
    label = `${verb} ${result.quantity ?? ""} ${result.ticker}`.trim();
    if (!success && result.reason) label += ` — ${result.reason}`;
  } else {
    const action = result.action === "remove" ? "Removed" : "Added";
    label = `${action} ${result.ticker}`;
    if (!success && result.reason) label += ` — ${result.reason}`;
  }
  return (
    <div className={`mt-1 flex items-center gap-1 text-[11px] ${color}`}>
      <span>{icon}</span>
      <span>{label}</span>
    </div>
  );
}

export default function ChatPanel() {
  const { chatMessages, chatLoading, chatPanelOpen, sendChatMessage } = useAppState();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [chatMessages, chatLoading]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || chatLoading) return;
    setInput("");
    await sendChatMessage(text);
  }

  if (!chatPanelOpen) return null;

  return (
    <aside
      className="flex h-full w-[340px] flex-col border-l border-[--color-border-muted] bg-[--color-bg-panel]"
      data-testid="chat-panel"
    >
      <div className="flex items-center justify-between border-b border-[--color-border-muted] px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-[--color-text-secondary]">
          AI Copilot
        </h2>
        <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
          {chatLoading ? "Thinking…" : "Ready"}
        </span>
      </div>
      <div ref={scrollRef} className="flex-1 space-y-2 overflow-y-auto p-3" data-testid="chat-history">
        {chatMessages.length === 0 ? (
          <div className="rounded border border-dashed border-[--color-border-muted] p-3 text-center text-xs text-[--color-text-muted]">
            Ask FinAlly about your portfolio, request analysis, or have it execute trades.
          </div>
        ) : null}
        {chatMessages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-[--color-accent-blue]/15 text-[--color-text-primary]"
                  : "bg-[--color-bg-panel-2] text-[--color-text-primary]"
              }`}
              data-testid={`chat-msg-${msg.role}`}
            >
              <div className="whitespace-pre-wrap leading-snug">{msg.content}</div>
              {msg.action_results?.map((r, j) => (
                <ActionBadge key={j} result={r} />
              ))}
            </div>
          </div>
        ))}
        {chatLoading ? (
          <div className="flex justify-start" data-testid="chat-loading">
            <div className="rounded-lg bg-[--color-bg-panel-2] px-3 py-2 text-sm text-[--color-text-muted]">
              <span className="inline-flex gap-1">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[--color-text-muted]" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[--color-text-muted] [animation-delay:0.15s]" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[--color-text-muted] [animation-delay:0.3s]" />
              </span>
            </div>
          </div>
        ) : null}
      </div>
      <form
        onSubmit={submit}
        className="flex flex-col gap-2 border-t border-[--color-border-muted] p-3"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(e);
            }
          }}
          placeholder="Ask FinAlly…"
          rows={2}
          className="resize-none rounded border border-[--color-border-muted] bg-[--color-bg-base] px-2 py-1.5 text-sm text-[--color-text-primary] focus:border-[--color-accent-blue] focus:outline-none"
          data-testid="chat-input"
        />
        <button
          type="submit"
          disabled={chatLoading || !input.trim()}
          className="self-end rounded-md bg-[--color-accent-purple] px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          data-testid="chat-send"
        >
          Send
        </button>
      </form>
    </aside>
  );
}
