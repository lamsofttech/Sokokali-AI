import { Panel, Pill } from "./ui";

const ITEMS = [
  { name: "Cloud deployment", detail: "Docker, PostgreSQL, Redis, CI and monitoring for 24/7 running", phase: "Phase 7" },
  { name: "Stream output", detail: "Send the presenter and voice to OBS / the livestream", phase: "Phase 7" },
  { name: "Real platform connector", detail: "TikTok needs officially authorized access first; YouTube/Twitch are options", phase: "Later" },
];

export function ComingNextPanel() {
  return (
    <Panel title="Coming next" subtitle="What the plan covers next">
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
