import { Panel, Pill } from "./ui";

const ITEMS = [
  { name: "Broadcast controls", detail: "Start, pause and stop the livestream simulation (admin login)", phase: "Phase 6" },
  { name: "Livestream feed", detail: "Simulated viewer comments over WebSocket", phase: "Phase 6" },
  { name: "Gamification", detail: "Trivia, prediction polls and community milestones", phase: "Phase 6" },
];

export function ComingNextPanel() {
  return (
    <Panel title="Coming next" subtitle="Dashboard sections waiting on backend features">
      <ul className="space-y-2">
        {ITEMS.map((item) => (
          <li key={item.name} className="flex items-start justify-between gap-3 text-sm">
            <div>
              <p className="font-medium text-zinc-300">{item.name}</p>
              <p className="text-xs text-zinc-500">{item.detail}</p>
            </div>
            <Pill>{item.phase}</Pill>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
