import { useCallback } from "react";

import { usePolling } from "../hooks/usePolling";
import type { SokokaliApi } from "../services/api";
import { percent } from "../services/format";
import type { ModelMetrics } from "../services/types";
import { ErrorNote, Panel, Pill } from "./ui";

const LABELS: Record<ModelMetrics["model"], string> = {
  baseline: "Baseline (frequencies)",
  poisson: "Poisson (expected goals)",
  elo: "Elo ratings",
  blend: "Blend (live model)",
};

export function ModelPanel({ client }: { client: SokokaliApi }) {
  const fetchReport = useCallback(() => client.modelEvaluation(), [client]);
  const { data, error, loading, refresh } = usePolling(fetchReport, 300_000);
  const best = data?.metrics.reduce<ModelMetrics | null>(
    (min, m) => (min === null || m.log_loss < min.log_loss ? m : min),
    null,
  );
  const baseline = data?.metrics.find((m) => m.model === "baseline");
  const blend = data?.metrics.find((m) => m.model === "blend");
  const beatsBaseline = baseline && blend ? blend.log_loss < baseline.log_loss : null;

  return (
    <Panel
      title="Model accuracy"
      subtitle="Walk-forward backtest: each match predicted using only earlier matches"
      actions={
        beatsBaseline !== null && (
          <Pill tone={beatsBaseline ? "ok" : "warn"}>{beatsBaseline ? "Beats baseline" : "Below baseline"}</Pill>
        )
      }
    >
      {error && <ErrorNote message={`Evaluation unavailable: ${error}`} onRetry={refresh} />}
      {loading && !data && <p className="text-sm text-zinc-400">Running backtest...</p>}
      {data && data.metrics.length === 0 && (
        <p className="text-sm text-zinc-400">Not enough finished matches to evaluate yet.</p>
      )}
      {data && data.metrics.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-zinc-400">
                <tr>
                  <th className="pb-2 font-medium">Model</th>
                  <th className="pb-2 text-right font-medium">Log loss</th>
                  <th className="pb-2 text-right font-medium">Brier</th>
                  <th className="pb-2 text-right font-medium">Accuracy</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {data.metrics.map((m) => (
                  <tr key={m.model} className={m.model === best?.model ? "text-emerald-200" : "text-zinc-200"}>
                    <td className="py-2">
                      {LABELS[m.model]}
                      {m.model === best?.model && <span className="sr-only"> (best)</span>}
                    </td>
                    <td className="py-2 text-right tabular-nums">{m.log_loss.toFixed(3)}</td>
                    <td className="py-2 text-right tabular-nums">{m.brier_score.toFixed(3)}</td>
                    <td className="py-2 text-right tabular-nums">{percent(m.accuracy)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[11px] text-zinc-500">
            {data.matches_evaluated} matches · {data.competitions.join(", ")} · outcomes: home{" "}
            {percent(data.outcome_frequencies.home_win)}, draw {percent(data.outcome_frequencies.draw)}, away{" "}
            {percent(data.outcome_frequencies.away_win)}. Lower log loss and Brier are better.
          </p>
        </>
      )}
    </Panel>
  );
}
