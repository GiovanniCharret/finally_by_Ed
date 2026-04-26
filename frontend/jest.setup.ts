import "@testing-library/jest-dom";

// Polyfill for jsdom: ResizeObserver
if (typeof (global as unknown as { ResizeObserver?: unknown }).ResizeObserver === "undefined") {
  (global as unknown as { ResizeObserver: unknown }).ResizeObserver =
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
}

// jsdom does not implement EventSource — provide a noop mock
if (typeof (global as unknown as { EventSource?: unknown }).EventSource === "undefined") {
  class EventSourceMock {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSED = 2;
    readyState = EventSourceMock.CONNECTING;
    addEventListener() {}
    removeEventListener() {}
    close() {
      this.readyState = EventSourceMock.CLOSED;
    }
  }
  (global as unknown as { EventSource: unknown }).EventSource = EventSourceMock;
}
