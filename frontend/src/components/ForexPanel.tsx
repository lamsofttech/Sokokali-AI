import { useCallback } from "react";

import { usePolling } from "../hooks/usePolling";
import type { SokokaliApi } from "../services/api";
import type { ForexSignal } from "../services/types";
import { ErrorNote, Panel, Pill, SimulatedTag } from "./ui";

const DIRECTION_TONE = { buy: "ok", sell: "bad", neutral: "neutral" } as const;

export function ForexPanel({ client }: { client: SokokaliApi }) {
  const fetchSignals = useCallback(() => client.forexSignals(), [client]);
  const { data, error, loading, refresh } = usePolling(fetchSignals, 60_000);
  const signals = data?.signals ?? [];
  const simulated = signals.some((s) => s.freshness.is_simulated);

  return (
    <Panel
      title="Forex signals"
      subtitle="Hourly technical outlook"
      actions={simulated && <SimulatedTag />}
    >
      {error && <ErrorNote message={`Forex signals unavailable: ${error}`} onRetry={refresh} />}
      {loading && !data && <p className="text-sm text-zinc-400">Loading signals...</p>}
      {signals.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-zinc-400">
                <tr>
                  <th className="pb-2 font-medium">Pair</th>
                  <th className="pb-2 font-medium">Signal</th>
                  <th className="pb-2 text-right font-medium">Price</th>
                  <th className="pb-2 text-right font-medium">RSI</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {signals.map((s) => (
                  <SignalRow key={s.symbol} signal={s} />
                ))}
              </tbody>
            </table>
          </div>
          {!signals[0]?.trade_levels_enabled && (
            <p className="mt-3 text-[11px] text-zinc-500">
              Entry, stop-loss and take-profit levels are switched off pending a licensing review.
            </p>
          )}
          <p className="mt-2 text-[11px] text-zinc-500">{signals[0]?.disclaimer}</p>
        </>
      )}
    </Panel>
  );
}

function SignalRow({ signal: s }: { signal: ForexSignal }) {
  return (
    <tr title={s.key_factors.join("\n")}>
      <td className="py-2 font-medium text-zinc-100">{s.display_name}</td>
      <td className="py-2">
        <Pill tone={DIRECTION_TONE[s.direction]}>
          {s.direction.toUpperCase()} · {s.strength}
        </Pill>
        {s.stop_loss !== null && s.take_profit !== null && (
          <span className="ml-2 text-xs text-zinc-400">
            SL {s.stop_loss} · TP {s.take_profit}
          </span>
        )}
      </td>
      <td className="py-2 text-right text-zinc-200 tabular-nums">{s.price}</td>
      <td className="py-2 text-right text-zinc-400 tabular-nums">{s.indicators.rsi.toFixed(0)}</td>
    </tr>
  );
}
