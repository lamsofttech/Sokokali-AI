import type { RequestEvent } from "../services/api";
import { clock } from "../services/format";
import { Panel } from "./ui";

export function ErrorLogPanel({ events }: { events: RequestEvent[] }) {
  const errors = events.filter((e) => !e.ok).slice(0, 20);
  return (
    <Panel title="Error log" subtitle="Failed API requests from this browser session">
      {errors.length === 0 ? (
        <p className="text-sm text-zinc-400">No errors.</p>
      ) : (
        <ul className="max-h-56 space-y-1.5 overflow-y-auto font-mono text-xs">
          {errors.map((e) => (
            <li key={e.id} className="text-red-200">
              <span className="text-zinc-500">{clock(e.at)}</span> {e.method} {e.path}{" "}
              <span className="text-red-300">{e.status ?? "no response"}</span> {e.error}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
