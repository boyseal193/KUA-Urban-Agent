"use client";

import * as React from "react";

/**
 * Lightweight WebSocket hook — wired up but not required.
 *
 * Set NEXT_PUBLIC_WS_URL in env to enable. Falls back to a no-op
 * if no URL is provided so the rest of the app doesn't blow up.
 */
type WSStatus = "idle" | "connecting" | "open" | "closed" | "error";

export function useWebSocket<T = unknown>(
  url: string | undefined = process.env.NEXT_PUBLIC_WS_URL,
  opts: {
    onMessage?: (msg: T) => void;
    onOpen?: () => void;
    onClose?: () => void;
    reconnect?: boolean;
  } = {}
) {
  const [status, setStatus] = React.useState<WSStatus>("idle");
  const wsRef = React.useRef<WebSocket | null>(null);
  const optsRef = React.useRef(opts);
  optsRef.current = opts;

  React.useEffect(() => {
    if (!url) return;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (cancelled) return;
      setStatus("connecting");
      try {
        const ws = new WebSocket(url!);
        wsRef.current = ws;

        ws.onopen = () => {
          setStatus("open");
          optsRef.current.onOpen?.();
        };
        ws.onmessage = (e) => {
          try {
            optsRef.current.onMessage?.(JSON.parse(e.data) as T);
          } catch {
            optsRef.current.onMessage?.(e.data as unknown as T);
          }
        };
        ws.onclose = () => {
          setStatus("closed");
          optsRef.current.onClose?.();
          if (optsRef.current.reconnect && !cancelled) {
            retryTimer = setTimeout(connect, 2000);
          }
        };
        ws.onerror = () => setStatus("error");
      } catch {
        setStatus("error");
      }
    }

    connect();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, [url]);

  const send = React.useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === "string" ? data : JSON.stringify(data));
    }
  }, []);

  return { status, send };
}
