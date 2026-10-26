import { humanize } from "../services/format";
import type { GamificationStatus } from "../services/types";
import { Panel, Pill } from "./ui";

export function GamificationPanel({ status }: { status: GamificationStatus | null }) {
  if (!status) {
    return (
      <Panel title="Engagement" subtitle="Milestones, trivia, polls and leaderboard">
        <p className="text-sm text-zinc-400">Waiting for the live feed...</p>
      </Panel>
    );
  }
  const { totals, trivia, poll, last_poll_result: lastPoll } = status;
  const pollTotal = poll ? poll.votes.home + poll.votes.draw + poll.votes.away : 0;

  return (
    <Panel
      title="Engagement"
      subtitle={status.rules}
      actions={<Pill>Outfit: {humanize(status.outfit)} · {humanize(status.background)}</Pill>}
    >
      <div className="space-y-4 text-sm">
        <dl className="grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
          {(Object.keys(totals) as (keyof typeof totals)[]).map((k) => (
            <div key={k}>
              <dt className="text-[11px] text-zinc-400 capitalize">{k}</dt>
              <dd className="font-semibold tabular-nums">{totals[k]}</dd>
            </div>
          ))}
        </dl>

        {trivia && (
          <div className="rounded-lg bg-zinc-950/60 p-3">
            <p className="text-xs font-semibold text-emerald-300">TRIVIA · {trivia.answers} answers</p>
            <p className="mt-1 text-zinc-100">{trivia.question_en}</p>
            <p className="text-xs text-zinc-400">{trivia.question_sw}</p>
            <p className="mt-1 text-xs text-zinc-300">{trivia.options.join("   ")}</p>
            {trivia.winners.length > 0 && <p className="mt-1 text-xs text-emerald-200">Correct: {trivia.winners.join(", ")}</p>}
          </div>
        )}

        {poll && (
          <div className="rounded-lg bg-zinc-950/60 p-3">
            <p className="text-xs font-semibold text-sky-300">FANS' POLL · {pollTotal} votes</p>
            <p className="mt-1 text-zinc-100">
              {poll.home_team} vs {poll.away_team}
            </p>
            <PollBars votes={poll.votes} home={poll.home_team} away={poll.away_team} />
          </div>
        )}
        {!poll && lastPoll && lastPoll.total > 0 && (
          <div className="text-xs text-zinc-400">
            Last poll, {lastPoll.home_team} vs {lastPoll.away_team} ({lastPoll.total} votes):
            <PollBars votes={lastPoll.votes} home={lastPoll.home_team} away={lastPoll.away_team} />
          </div>
        )}

        <ul className="space-y-2">
          {status.milestones.map((m) => (
            <li key={m.id}>
              <div className="flex justify-between text-xs">
                <span className={m.reached ? "text-emerald-300" : "text-zinc-300"}>
                  {m.reached ? "✓ " : ""}
                  {m.label}
                </span>
                <span className="text-zinc-400 tabular-nums">
                  {Math.min(m.current, m.target)}/{m.target}
                </span>
              </div>
              <div
                className="mt-1 h-1.5 overflow-hidden rounded-full bg-zinc-800"
                role="progressbar"
                aria-label={m.label}
                aria-valuemin={0}
                aria-valuemax={m.target}
                aria-valuenow={Math.min(m.current, m.target)}
              >
                <div
                  className={m.reached ? "h-full bg-emerald-500" : "h-full bg-sky-500"}
                  style={{ width: `${Math.min(100, (m.current / m.target) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>

        {status.leaderboard.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-semibold text-zinc-300">Top fans (free participation)</p>
            <ol className="space-y-0.5 text-xs">
              {status.leaderboard.map((entry, i) => (
                <li key={entry.viewer_name} className="flex justify-between">
                  <span>
                    {i + 1}. {entry.viewer_name}
                  </span>
                  <span className="tabular-nums text-zinc-400">{entry.points} pts</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </Panel>
  );
}

function PollBars({ votes, home, away }: { votes: { home: number; draw: number; away: number }; home: string; away: string }) {
  const total = votes.home + votes.draw + votes.away || 1;
  const rows = [
    { label: `1 · ${home}`, n: votes.home },
    { label: "X · Draw", n: votes.draw },
    { label: `2 · ${away}`, n: votes.away },
  ];
  return (
    <ul className="mt-2 space-y-1 text-xs">
      {rows.map((r) => (
        <li key={r.label} className="flex items-center gap-2">
          <span className="w-32 truncate text-zinc-300">{r.label}</span>
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-800">
            <span className="block h-full bg-sky-500" style={{ width: `${(r.n / total) * 100}%` }} />
          </span>
          <span className="w-6 text-right tabular-nums text-zinc-400">{r.n}</span>
        </li>
      ))}
    </ul>
  );
}
