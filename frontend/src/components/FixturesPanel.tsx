import { useCallback, useEffect, useState } from "react";

import { usePolling } from "../hooks/usePolling";
import type { SokokaliApi } from "../services/api";
import { kickoff } from "../services/format";
import type { Prediction } from "../services/types";
import { ProbabilityBar } from "./ProbabilityBar";
import { ErrorNote, Panel, SimulatedTag } from "./ui";

export function FixturesPanel({ client }: { client: SokokaliApi }) {
  const fetchFixtures = useCallback(() => client.fixtures(10), [client]);
  const { data, error, loading, refresh } = usePolling(fetchFixtures, 60_000);
  const [selected, setSelected] = useState<string | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [predictionError, setPredictionError] = useState<string | null>(null);

  // Select the first fixture once fixtures arrive.
  useEffect(() => {
    if (!selected && data?.fixtures[0]) setSelected(data.fixtures[0].match_id);
  }, [data, selected]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setPredictionError(null);
    client
      .prediction(selected)
      .then((p) => !cancelled && setPrediction(p))
      .catch((err: Error) => !cancelled && setPredictionError(err.message));
    return () => {
      cancelled = true;
    };
  }, [client, selected]);

  return (
    <Panel
      title="Fixtures & predictions"
      subtitle="Select a match to see the model's probabilities"
      actions={data?.freshness.is_simulated && <SimulatedTag />}
    >
      {error && <ErrorNote message={`Fixtures unavailable: ${error}`} onRetry={refresh} />}
      {loading && !data && <p className="text-sm text-zinc-400">Loading fixtures...</p>}
      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <ul className="space-y-1">
            {data.fixtures.map((f) => (
              <li key={f.match_id}>
                <button
                  onClick={() => setSelected(f.match_id)}
                  aria-pressed={selected === f.match_id}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                    selected === f.match_id
                      ? "bg-emerald-500/10 ring-1 ring-emerald-500/40"
                      : "hover:bg-zinc-800/70"
                  }`}
                >
                  <span className="block font-medium text-zinc-100">
                    {f.home_team.name} vs {f.away_team.name}
                  </span>
                  <span className="block text-xs text-zinc-400">
                    {kickoff(f.kickoff)} · {f.competition}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <div className="rounded-lg bg-zinc-950/60 p-3">
            {predictionError && <ErrorNote message={`Prediction unavailable: ${predictionError}`} />}
            {prediction && prediction.match_id === selected && (
              <div className="space-y-3">
                <div>
                  <p className="text-sm font-semibold text-zinc-100">
                    {prediction.home_team} vs {prediction.away_team}
                  </p>
                  <p className="text-xs text-zinc-400">
                    Expected goals {prediction.expected_goals.home} – {prediction.expected_goals.away} · model{" "}
                    {prediction.model_version}
                  </p>
                </div>
                <ProbabilityBar
                  home={prediction.probabilities.home_win}
                  draw={prediction.probabilities.draw}
                  away={prediction.probabilities.away_win}
                  homeLabel={prediction.home_team}
                  awayLabel={prediction.away_team}
                />
                <ul className="list-disc space-y-1 pl-4 text-xs text-zinc-300">
                  {prediction.key_factors.map((factor) => (
                    <li key={factor}>{factor}</li>
                  ))}
                </ul>
                <p className="text-[11px] text-zinc-500">{prediction.disclaimer}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
