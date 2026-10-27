import { useEffect, useRef, useState } from "react";

import type {
  BroadcastStatus,
  GamificationStatus,
  GameUpdate,
  LiveEventData,
  LiveMessage,
  SayData,
} from "../services/types";

export interface FeedItem {
  id: number;
  at: string;
  kind: "event" | "say" | "game" | "alert";
  event?: LiveEventData;
  say?: SayData;
  game?: GameUpdate;
  alert?: string;
}

export interface LiveFeed {
  connected: boolean;
  /** Set when the server refused the connection (wrong or missing admin token). */
  authError: boolean;
  state: BroadcastStatus | null;
  gamification: GamificationStatus | null;
  feed: FeedItem[];
}

interface Handlers {
  onSay?: (say: SayData) => void;
  onGame?: (update: GameUpdate) => void;
  /** Called when trivia/poll/milestone data may have changed. */
  onGamificationChanged?: () => void;
}

const MAX_ITEMS = 80;

export function liveSocketUrl(token: string, location: Pick<Location, "protocol" | "host"> = window.location): string {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${scheme}://${location.host}/ws/live${query}`;
}

/** Live broadcast feed over WebSocket, reconnecting with backoff (1 s doubling to 15 s). */
export function useLiveFeed(token: string, handlers: Handlers = {}): LiveFeed & { setGamification: (g: GamificationStatus) => void } {
  const [connected, setConnected] = useState(false);
  const [authError, setAuthError] = useState(false);
  const [state, setState] = useState<BroadcastStatus | null>(null);
  const [gamification, setGamification] = useState<GamificationStatus | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let delay = 1000;
    let closed = false;
    let nextId = 1;

    const add = (item: Omit<FeedItem, "id">) =>
      setFeed((prev) => [{ ...item, id: nextId++ }, ...prev].slice(0, MAX_ITEMS));

    const handle = (message: LiveMessage, live: boolean) => {
      switch (message.type) {
        case "snapshot":
          setState(message.data.state);
          setGamification(message.data.gamification);
          // Replay recent history (oldest first, so the newest ends on top) without speaking it again.
          message.data.recent.forEach((m) => handle(m, false));
          break;
        case "state":
          setState(message.data);
          break;
        case "event":
          add({ at: message.at, kind: "event", event: message.data });
          break;
        case "say":
          add({ at: message.at, kind: "say", say: message.data });
          if (live) handlersRef.current.onSay?.(message.data);
          break;
        case "game":
          add({ at: message.at, kind: "game", game: message.data });
          if (live) {
            handlersRef.current.onGame?.(message.data);
            handlersRef.current.onGamificationChanged?.();
          }
          break;
        case "alert":
          add({ at: message.at, kind: "alert", alert: message.data.message });
          break;
      }
    };

    const connect = () => {
      socket = new WebSocket(liveSocketUrl(token));
      socket.onopen = () => {
        delay = 1000;
        setConnected(true);
        setAuthError(false);
      };
      socket.onmessage = (event) => {
        try {
          handle(JSON.parse(String(event.data)) as LiveMessage, true);
        } catch {
          // Ignore malformed messages rather than dropping the connection.
        }
      };
      socket.onclose = (event) => {
        setConnected(false);
        if (closed) return;
        if (event.code === 1008) {
          setAuthError(true); // policy violation: wrong token; wait for the user to change it
          return;
        }
        retry = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 15_000);
      };
    };

    setFeed([]);
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, [token]);

  return { connected, authError, state, gamification, feed, setGamification };
}
