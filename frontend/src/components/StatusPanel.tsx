import type { PollingState } from "../hooks/usePolling";
import type { RequestEvent } from "../services/api";
import { duration, humanize } from "../services/format";
import type { StatusResponse } from "../services/types";
import { ErrorNote, Panel, Pill, type Tone } from "./ui";

const STATUS_TONE: Record<string, Tone> = { ok: "ok", degraded: "warn", disabled: "neutral", down: "bad" };

export function StatusPanel({ status, events }: { status: PollingState<StatusResponse>; events: RequestEvent[] }) {
  const ok = events.filter((e) => e.ok);
  const recent = ok.slice(0, 20);
  const avg = recent.length ? recent.reduce((sum, e) => sum + e.durationMs, 0) / recent.length : null;
  const chat = ok.find((e) => e.path === "/api/v1/chat");
  const data = status.data;

  return (
    <Panel title="System status" subtitle={data ? `v${data.version} · ${data.environment}` : undefined}>
      {status.error && <ErrorNote message={`Backend unreachable: ${status.error}`} onRetry={status.refresh} />}
      {data && (
        <ul className="space-y-2">
          {data.components.map((c) => (
            <li key={c.name} className="flex items-start justify-between gap-3 text-sm">
              <div className="min-w-0">
                <p className="font-medium text-zinc-200 capitalize">{humanize(c.name)}</p>
                <p className="text-xs text-zinc-400">{c.detail}</p>
              </div>
              <Pill tone={STATUS_TONE[c.status] ?? "neutral"}>{c.status}</Pill>
            </li>
          ))}
        </ul>
      )}
      <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-zinc-800 pt-3 text-center">
        <Stat label="Uptime" value={data ? duration(data.uptime_seconds) : "–"} />
        <Stat label="Avg API latency" value={avg === null ? "–" : `${Math.round(avg)} ms`} />
        <Stat label="Last chat reply" value={chat ? `${(chat.durationMs / 1000).toFixed(1)} s` : "–"} />
      </dl>
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] text-zinc-400">{label}</dt>
      <dd className="text-sm font-semibold text-zinc-100 tabular-nums">{value}</dd>
    </div>
  );
}
