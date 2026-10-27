import { useEffect, useState } from "react";

import type { SokokaliApi } from "../services/api";
import { duration, humanize } from "../services/format";
import type { Audience, BroadcastStatus, Segment } from "../services/types";
import { ErrorNote, Panel, Pill, type Tone } from "./ui";

const STATE_TONE: Record<BroadcastStatus["state"], Tone> = { running: "ok", paused: "warn", stopped: "neutral" };
const AUDIENCES: { id: Audience; label: string }[] = [
  { id: "simulated", label: "Simulated viewers (testing)" },
  { id: "relay", label: "TikTok LIVE via moderator relay" },
  { id: "tiktok", label: "TikTok API (not authorized yet)" },
];

const SEGMENTS: { id: Segment; label: string }[] = [
  { id: "trivia", label: "Trivia" },
  { id: "poll", label: "Fans' poll" },
  { id: "match_preview", label: "Match preview" },
  { id: "forex", label: "Forex outlook" },
  { id: "responsible_gambling", label: "Responsible gambling" },
];

interface Props {
  client: SokokaliApi;
  state: BroadcastStatus | null;
  connected: boolean;
  authError: boolean;
  token: string;
  onTokenChange: (token: string) => void;
}

export function BroadcastPanel({ client, state, connected, authError, token, onTokenChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tokenDraft, setTokenDraft] = useState(token);
  const [audience, setAudience] = useState<Audience>(state?.audience ?? "simulated");
  useEffect(() => {
    if (state && state.state !== "stopped") setAudience(state.audience); // follow the running show
  }, [state]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const running = state?.state === "running";
  const paused = state?.state === "paused";
  const rejected = Object.entries(state?.comments_rejected ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <Panel
      title="Broadcast control"
      subtitle={
        state
          ? `Live source: ${state.source}${state.source_is_simulated ? " (simulated viewers)" : ""}`
          : "Connecting to the live feed..."
      }
      actions={
        <>
          <Pill tone={connected ? "ok" : "bad"}>{connected ? "Feed connected" : "Feed offline"}</Pill>
          {state && <Pill tone={STATE_TONE[state.state]}>{state.state.toUpperCase()}</Pill>}
        </>
      }
    >
      <div className="space-y-3 text-sm">
        <label className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
          Audience
          <select
            value={audience}
            disabled={busy || (state !== null && state.state !== "stopped")}
            onChange={(e) => setAudience(e.target.value as Audience)}
            className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-100 disabled:opacity-60"
          >
            {AUDIENCES.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
          {state !== null && state.state !== "stopped" && <span>(stop the show to change)</span>}
        </label>

        <div className="flex flex-wrap gap-2">
          <button
            disabled={busy || running}
            onClick={() => void run(() => client.broadcast("start", paused ? undefined : audience))}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 font-semibold text-white hover:bg-emerald-500 disabled:opacity-40"
          >
            {paused ? "Resume" : "Start"}
          </button>
          <button
            disabled={busy || !running}
            onClick={() => void run(() => client.broadcast("pause"))}
            className="rounded-lg border border-amber-500/50 px-3 py-1.5 text-amber-200 hover:bg-amber-500/10 disabled:opacity-40"
          >
            Pause
          </button>
          <button
            disabled={busy || state?.state === "stopped"}
            onClick={() => void run(() => client.broadcast("stop"))}
            className="rounded-lg border border-red-500/50 px-3 py-1.5 text-red-200 hover:bg-red-500/10 disabled:opacity-40"
          >
            Stop
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-zinc-400">Run now:</span>
          {SEGMENTS.map((s) => (
            <button
              key={s.id}
              disabled={busy || !running}
              onClick={() => void run(() => client.runSegment(s.id))}
              className="rounded-md border border-zinc-700 px-2 py-1 text-zinc-200 hover:border-emerald-500 disabled:opacity-40"
            >
              {s.label}
            </button>
          ))}
        </div>

        {error && <ErrorNote message={error} />}
        {state?.source_error && <ErrorNote message={state.source_error} />}

        {state && (
          <dl className="grid grid-cols-3 gap-2 border-t border-zinc-800 pt-3 text-center sm:grid-cols-6">
            <Stat label="Uptime" value={state.started_at ? duration(state.uptime_seconds) : "–"} />
            <Stat label="Events" value={state.events_received} />
            <Stat label="Answered" value={state.replies} />
            <Stat label="Segments" value={state.segments} />
            <Stat label="Queued" value={state.queue_size} />
            <Stat label="Errors" value={state.errors} />
          </dl>
        )}
        {rejected.length > 0 && (
          <p className="text-xs text-zinc-400">
            Filtered: {rejected.map(([reason, n]) => `${humanize(reason)} ${n}`).join(" · ")}
          </p>
        )}
        {state?.last_error && <p className="text-xs text-red-300">Last error: {state.last_error}</p>}

        <form
          className="flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-3 text-xs"
          onSubmit={(e) => {
            e.preventDefault();
            onTokenChange(tokenDraft.trim());
          }}
        >
          <label htmlFor="admin-token" className="text-zinc-400">
            Admin token
          </label>
          <input
            id="admin-token"
            type="password"
            autoComplete="off"
            value={tokenDraft}
            onChange={(e) => setTokenDraft(e.target.value)}
            placeholder="Not needed in local development"
            className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-100"
          />
          <button type="submit" className="rounded border border-zinc-700 px-2 py-1 hover:border-emerald-500">
            Save
          </button>
          {authError && <span className="w-full text-red-300">The live feed rejected this token.</span>}
        </form>
      </div>
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-[11px] text-zinc-400">{label}</dt>
      <dd className="font-semibold text-zinc-100 tabular-nums">{value}</dd>
    </div>
  );
}
