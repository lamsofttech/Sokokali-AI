import { percent } from "../services/format";

interface Props {
  home: number;
  draw: number;
  away: number;
  homeLabel: string;
  awayLabel: string;
}

/** Home / draw / away probabilities as one stacked bar with labels. */
export function ProbabilityBar({ home, draw, away, homeLabel, awayLabel }: Props) {
  const segments = [
    { key: "home", label: homeLabel, value: home, color: "bg-emerald-500" },
    { key: "draw", label: "Draw", value: draw, color: "bg-zinc-400" },
    { key: "away", label: awayLabel, value: away, color: "bg-sky-500" },
  ];
  return (
    <div>
      <div
        className="flex h-2.5 overflow-hidden rounded-full bg-zinc-800"
        role="img"
        aria-label={segments.map((s) => `${s.label} ${percent(s.value)}`).join(", ")}
      >
        {segments.map((s) => (
          <div key={s.key} className={s.color} style={{ width: `${s.value * 100}%` }} />
        ))}
      </div>
      <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
        {segments.map((s) => (
          <div key={s.key} className={s.key === "draw" ? "text-center" : s.key === "away" ? "text-right" : ""}>
            <dt className="truncate text-zinc-400">{s.label}</dt>
            <dd className="font-semibold text-zinc-100 tabular-nums">{percent(s.value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
