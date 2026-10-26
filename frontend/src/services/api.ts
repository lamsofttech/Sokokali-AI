// Small typed client for the Sokokali API. Every request is timed and reported to
// subscribers, which is how the dashboard shows API latency and the error log.

import type {
  BacktestReport,
  BroadcastStatus,
  GamificationStatus,
  Segment,
  ChatRequest,
  ChatResponse,
  FixtureList,
  ForexSignalList,
  HealthResponse,
  Prediction,
  StatusResponse,
} from "./types";

export interface RequestEvent {
  id: number;
  method: string;
  path: string;
  status: number | null; // null when the request never got a response
  ok: boolean;
  durationMs: number;
  at: Date;
  error?: string;
}

export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type Listener = (event: RequestEvent) => void;

const DEFAULT_TIMEOUT_MS = 10_000;
const CHAT_TIMEOUT_MS = 60_000; // Claude replies can take several seconds, plus tool calls

export class SokokaliApi {
  private readonly baseUrl: string;
  private readonly listeners = new Set<Listener>();
  private nextId = 1;
  /** Sent as a Bearer token on admin requests (broadcast controls). */
  adminToken = "";

  constructor(baseUrl = "") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(event: Omit<RequestEvent, "id">): void {
    const full = { ...event, id: this.nextId++ };
    this.listeners.forEach((listener) => listener(full));
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    admin = false,
  ): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const started = performance.now();
    const at = new Date();
    let status: number | null = null;
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: {
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(admin && this.adminToken ? { Authorization: `Bearer ${this.adminToken}` } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      status = response.status;
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        throw new ApiError(errorDetail(data) ?? `HTTP ${response.status}`, response.status);
      }
      this.emit({ method, path, status, ok: true, durationMs: performance.now() - started, at });
      return data as T;
    } catch (err) {
      const error =
        err instanceof ApiError
          ? err
          : new ApiError(
              controller.signal.aborted ? `Timed out after ${timeoutMs / 1000}s` : "Backend unreachable",
              status,
            );
      this.emit({ method, path, status, ok: false, durationMs: performance.now() - started, at, error: error.message });
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  health = () => this.request<HealthResponse>("GET", "/health");
  status = () => this.request<StatusResponse>("GET", "/api/v1/status");
  fixtures = (limit = 20) => this.request<FixtureList>("GET", `/api/v1/fixtures?limit=${limit}`);
  prediction = (matchId: string) =>
    this.request<Prediction>("GET", `/api/v1/predictions/${encodeURIComponent(matchId)}`);
  modelEvaluation = () => this.request<BacktestReport>("GET", "/api/v1/models/evaluation", undefined, 30_000);
  forexSignals = () => this.request<ForexSignalList>("GET", "/api/v1/forex/signals");
  broadcastStatus = () => this.request<BroadcastStatus>("GET", "/api/v1/broadcast/status");
  broadcast = (action: "start" | "pause" | "stop") =>
    this.request<BroadcastStatus>("POST", `/api/v1/broadcast/${action}`, undefined, DEFAULT_TIMEOUT_MS, true);
  runSegment = (segment: Segment) =>
    this.request<{ started: string }>("POST", `/api/v1/broadcast/segments/${segment}`, undefined, 60_000, true);
  gamification = () => this.request<GamificationStatus>("GET", "/api/v1/gamification/status");
  chat = (payload: ChatRequest) => this.request<ChatResponse>("POST", "/api/v1/chat", payload, CHAT_TIMEOUT_MS);
}

function errorDetail(data: unknown): string | null {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI validation errors: [{loc, msg, ...}]
      return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
    }
  }
  return null;
}

export const api = new SokokaliApi(import.meta.env.VITE_API_BASE_URL ?? "");
