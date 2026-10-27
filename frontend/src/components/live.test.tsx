import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { liveSocketUrl, useLiveFeed } from "../hooks/useLiveFeed";
import { SokokaliApi } from "../services/api";
import type { BroadcastStatus, GamificationStatus } from "../services/types";
import { jsonResponse } from "../test/fixtures";
import { BroadcastPanel } from "./BroadcastPanel";
import { GamificationPanel } from "./GamificationPanel";
import { LiveFeedPanel } from "./LiveFeedPanel";

const broadcastState: BroadcastStatus = {
  state: "running",
  source: "simulated",
  source_is_simulated: true,
  source_error: null,
  started_at: "2026-10-26T08:00:00Z",
  uptime_seconds: 125,
  queue_size: 3,
  replies: 7,
  segments: 2,
  events_received: 90,
  comments_rejected: { too_short: 4, moderated: 1 },
  errors: 0,
  last_error: null,
  speaking_until: null,
  connected_clients: 1,
};

const gamification: GamificationStatus = {
  totals: { viewers: 12, comments: 30, likes: 140, gifts: 2, follows: 1, shares: 0 },
  milestones: [
    { id: "likes-100", label: "100 likes: floodlights on", metric: "likes", target: 100, current: 140, reached: true },
    { id: "likes-500", label: "500 likes: away jersey", metric: "likes", target: 500, current: 140, reached: false },
  ],
  outfit: "home",
  background: "floodlights",
  trivia: {
    question_en: "Which club is nicknamed 'The Gunners'?",
    question_sw: "Klabu gani inaitwa 'The Gunners'?",
    options: ["A) Chelsea", "B) Liverpool", "C) Arsenal", "D) Tottenham"],
    closes_at: "2026-10-26T08:05:00Z",
    answers: 4,
    winners: ["Achieng"],
  },
  poll: null,
  leaderboard: [{ viewer_name: "Achieng", points: 11 }],
  last_poll_result: null,
  rules: "Points come only from free participation (comments, trivia, polls). Gifts are cosmetic only.",
};

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  open() {
    this.onopen?.();
  }
  send(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => vi.useRealTimers());

describe("useLiveFeed", () => {
  it("builds the socket URL with the admin token", () => {
    expect(liveSocketUrl("t o", { protocol: "https:", host: "x.test" })).toBe("wss://x.test/ws/live?token=t%20o");
    expect(liveSocketUrl("", { protocol: "http:", host: "localhost:5173" })).toBe("ws://localhost:5173/ws/live");
  });

  it("loads the snapshot without replaying speech, then speaks live replies", () => {
    const onSay = vi.fn();
    const { result } = renderHook(() => useLiveFeed("", { onSay }));
    const socket = FakeSocket.instances[0]!;
    act(() => {
      socket.open();
      socket.send({
        type: "snapshot",
        data: {
          state: broadcastState,
          gamification,
          recent: [
            { type: "say", at: "2026-10-26T07:59:00Z", data: { source: "poll", text: "older", speech: null } },
            { type: "say", at: "2026-10-26T08:00:00Z", data: { source: "trivia", text: "old", speech: null } },
          ],
        },
      });
    });
    expect(result.current.connected).toBe(true);
    expect(result.current.state?.replies).toBe(7);
    expect(result.current.feed.map((f) => f.say?.text)).toEqual(["old", "older"]); // newest first
    expect(onSay).not.toHaveBeenCalled();

    act(() => socket.send({ type: "say", at: "2026-10-26T08:01:00Z", data: { source: "viewer", text: "new", speech: null } }));
    expect(onSay).toHaveBeenCalledWith(expect.objectContaining({ text: "new" }));
    expect(result.current.feed[0]?.say?.text).toBe("new");
  });

  it("reconnects after a drop but not after an auth rejection", () => {
    const { result } = renderHook(() => useLiveFeed("bad"));
    act(() => FakeSocket.instances[0]!.onclose?.({ code: 1006 }));
    act(() => {
      vi.advanceTimersByTime(1100);
    });
    expect(FakeSocket.instances).toHaveLength(2);
    act(() => FakeSocket.instances[1]!.onclose?.({ code: 1008 }));
    expect(result.current.authError).toBe(true);
    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    expect(FakeSocket.instances).toHaveLength(2);
  });
});

describe("BroadcastPanel", () => {
  it("sends admin actions with the bearer token and shows stats", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...broadcastState, state: "paused" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new SokokaliApi();
    client.adminToken = "s3cret";
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(
      <BroadcastPanel client={client} state={broadcastState} connected authError={false} token="s3cret" onTokenChange={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: "Start" })).toBeDisabled(); // already running
    await user.click(screen.getByRole("button", { name: "Pause" }));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/broadcast/pause");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer s3cret");
    expect(screen.getByText("7")).toBeInTheDocument(); // answered
    expect(screen.getByText(/too short 4/)).toBeInTheDocument();
  });

  it("runs a segment on demand and shows errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Admin token required" }, 401)));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(
      <BroadcastPanel client={new SokokaliApi()} state={broadcastState} connected authError onTokenChange={vi.fn()} token="" />,
    );
    await user.click(screen.getByRole("button", { name: "Trivia" }));
    expect(await screen.findByText("Admin token required")).toBeInTheDocument();
    expect(screen.getByText("The live feed rejected this token.")).toBeInTheDocument();
  });

  it("saves the admin token", async () => {
    const onTokenChange = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(
      <BroadcastPanel client={new SokokaliApi()} state={null} connected={false} authError={false} token="" onTokenChange={onTokenChange} />,
    );
    await user.type(screen.getByLabelText("Admin token"), " abc ");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onTokenChange).toHaveBeenCalledWith("abc");
  });
});

describe("LiveFeedPanel", () => {
  it("shows events, filters and replies", () => {
    const base = { platform: "simulated", viewer_id: "v1", count: 1, gift_name: null, received_at: "", is_simulated: true };
    render(
      <LiveFeedPanel
        simulated
        feed={[
          { id: 3, at: "2026-10-26T08:00:03Z", kind: "say", say: { source: "viewer", viewer_name: "Achieng", comment: "Gor vs Ingwe?", text: "Wasee!", speech: null } },
          { id: 2, at: "2026-10-26T08:00:02Z", kind: "event", event: { ...base, event_id: "2", viewer_name: "Musa", kind: "gift", text: null, gift_name: "Rose" } },
          { id: 1, at: "2026-10-26T08:00:01Z", kind: "event", event: { ...base, event_id: "1", viewer_name: "Achieng", kind: "comment", text: "Gor vs Ingwe?", accepted: true, priority: 50 } },
        ]}
      />,
    );
    expect(screen.getByText("queued · priority 50")).toBeInTheDocument();
    expect(screen.getByText("sent a Rose (cosmetic effect only)")).toBeInTheDocument();
    expect(screen.getByText("Wasee!")).toBeInTheDocument();
    expect(screen.getByText("Simulated viewers")).toBeInTheDocument();
  });
});

describe("GamificationPanel", () => {
  it("shows totals, trivia, milestones and leaderboard", () => {
    render(<GamificationPanel status={gamification} />);
    expect(screen.getByText("Which club is nicknamed 'The Gunners'?")).toBeInTheDocument();
    expect(screen.getByText("Correct: Achieng")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "500 likes: away jersey" })).toHaveAttribute("aria-valuenow", "140");
    expect(screen.getByText("11 pts")).toBeInTheDocument();
    expect(screen.getByText(/Gifts are cosmetic only/)).toBeInTheDocument();
  });
});
