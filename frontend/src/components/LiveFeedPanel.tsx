import type { FeedItem } from "../hooks/useLiveFeed";
import { clock, humanize } from "../services/format";
import type { LiveEventData } from "../services/types";
import { Panel, Pill } from "./ui";

function eventText(e: LiveEventData): string {
  switch (e.kind) {
    case "join":
      return "joined the stream";
    case "like":
      return `liked ×${e.count}`;
    case "gift":
      return `sent a ${e.gift_name ?? "gift"} (cosmetic effect only)`;
    case "follow":
      return "followed";
    case "share":
      return "shared the stream";
    default:
      return e.text ?? "";
  }
}

export function LiveFeedPanel({ feed, simulated }: { feed: FeedItem[]; simulated: boolean }) {
  return (
    <Panel
      title="Live feed"
      subtitle="Viewer events and Sokokali's on-air replies, newest first"
      actions={simulated && <Pill tone="warn">Simulated viewers</Pill>}
      className="h-[34rem]"
    >
      {feed.length === 0 ? (
        <p className="text-sm text-zinc-400">Nothing yet. Start the broadcast to see viewers arrive.</p>
      ) : (
        <ul className="h-full space-y-2 overflow-y-auto pr-1 text-sm" aria-live="polite">
          {feed.map((item) => (
            <li key={item.id}>
              {item.kind === "event" && item.event && (
                <div className="flex items-start gap-2">
                  <span className="shrink-0 font-mono text-[11px] text-zinc-500">{clock(new Date(item.at))}</span>
                  <p className="min-w-0 text-zinc-300">
                    <span className="font-medium text-zinc-100">{item.event.viewer_name}</span>{" "}
                    <span className={item.event.kind === "comment" ? "text-zinc-100" : "text-zinc-400"}>
                      {eventText(item.event)}
                    </span>{" "}
                    {item.event.kind === "comment" &&
                      (item.event.accepted ? (
                        <Pill tone="info">queued · priority {item.event.priority}</Pill>
                      ) : (
                        item.event.reason && (
                          <Pill tone={item.event.reason === "moderated" ? "bad" : "neutral"}>{humanize(item.event.reason)}</Pill>
                        )
                      ))}
                  </p>
                </div>
              )}
              {item.kind === "say" && item.say && (
                <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
                  <p className="mb-0.5 text-[11px] font-semibold tracking-wide text-emerald-300 uppercase">
                    Sokokali{" "}
                    {item.say.viewer_name
                      ? `→ ${item.say.viewer_name}`
                      : `· ${humanize(item.say.source)}`}
                  </p>
                  {item.say.comment && <p className="text-xs text-zinc-400">“{item.say.comment}”</p>}
                  <p className="text-zinc-100">{item.say.text}</p>
                </div>
              )}
              {item.kind === "game" && item.game && (
                <p className="rounded-md bg-sky-500/10 px-3 py-1.5 text-sky-200">{item.game.message}</p>
              )}
              {item.kind === "alert" && (
                <p role="alert" className="rounded-md bg-red-500/10 px-3 py-1.5 text-red-200">
                  {item.alert}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
