import { type FormEvent, useEffect, useRef, useState } from "react";

import type { SokokaliApi } from "../services/api";
import { LANGUAGE_NAMES, humanize } from "../services/format";
import type { ChatResponse, Language } from "../services/types";
import { ProbabilityBar } from "./ProbabilityBar";
import { Panel, Pill, SimulatedTag } from "./ui";

interface Entry {
  id: number;
  viewer: string;
  message: string;
  response?: ChatResponse;
  error?: string;
}

const SUGGESTIONS = [
  "Sokokali, Arsenal na Chelsea nani atashinda?",
  "Niaje msee! Gor vs Leopards nani atawin?",
  "What are the upcoming fixtures?",
  "Liverpool form",
  "EUR/USD signal",
  "Nipe uchambuzi wa USD/KES",
];

const DIRECTION_TONE = { buy: "ok", sell: "bad", neutral: "neutral" } as const;

export function ChatPanel({ client, onReply }: { client: SokokaliApi; onReply?: (r: ChatResponse) => void }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [message, setMessage] = useState("");
  const [viewer, setViewer] = useState("fan-1");
  const [language, setLanguage] = useState<Language | "auto">("auto");
  const [pending, setPending] = useState(false);
  const nextId = useRef(1);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Scroll inside the chat box only (never the page), and only once there is something to show.
    const thread = threadRef.current;
    if (thread && (entries.length > 0 || pending)) thread.scrollTop = thread.scrollHeight;
  }, [entries, pending]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || pending) return;
    const id = nextId.current++;
    const viewerId = viewer.trim() || undefined;
    setEntries((prev) => [...prev, { id, viewer: viewerId ?? "anonymous", message: trimmed }]);
    setMessage("");
    setPending(true);
    try {
      const response = await client.chat({
        message: trimmed,
        viewer_id: viewerId,
        language: language === "auto" ? undefined : language,
      });
      setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, response } : e)));
      onReply?.(response);
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, error } : e)));
    } finally {
      setPending(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(message);
  }

  return (
    <Panel
      title="Live chat"
      subtitle="Send a message as a viewer and see how Sokokali answers"
      className="h-[42rem]"
      actions={
        entries.length > 0 && (
          <button
            onClick={() => setEntries([])}
            className="rounded-md px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          >
            Clear
          </button>
        )
      }
    >
      <div className="flex h-full flex-col gap-3">
        <div ref={threadRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1" aria-live="polite">
          {entries.length === 0 && (
            <div className="rounded-lg border border-dashed border-zinc-700 p-4 text-sm text-zinc-400">
              <p className="mb-3">Try one of these, or type your own:</p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => void send(s)}
                    className="rounded-full border border-zinc-700 px-3 py-1 text-xs text-zinc-200 hover:border-emerald-500 hover:text-white"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {entries.map((entry) => (
            <ChatEntry key={entry.id} entry={entry} />
          ))}
          {pending && (
            <p className="flex items-center gap-2 text-sm text-zinc-400">
              <span className="size-2 animate-pulse rounded-full bg-emerald-400" /> Sokokali is answering...
            </p>
          )}
        </div>

        <form onSubmit={onSubmit} className="space-y-2 border-t border-zinc-800 pt-3">
          <div className="flex gap-2">
            <label className="sr-only" htmlFor="chat-message">
              Message
            </label>
            <input
              id="chat-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              maxLength={500}
              placeholder="Andika ujumbe... / Type a message..."
              className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-emerald-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={pending || !message.trim()}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Send
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-400">
            <label className="flex items-center gap-1.5">
              Viewer ID
              <input
                value={viewer}
                onChange={(e) => setViewer(e.target.value.replace(/[^A-Za-z0-9_.:-]/g, ""))}
                maxLength={64}
                className="w-28 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-100 focus:border-emerald-500 focus:outline-none"
              />
            </label>
            <label className="flex items-center gap-1.5">
              Reply language
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as Language | "auto")}
                className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-100 focus:border-emerald-500 focus:outline-none"
              >
                <option value="auto">Auto-detect</option>
                {Object.entries(LANGUAGE_NAMES).map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </form>
      </div>
    </Panel>
  );
}

function ChatEntry({ entry }: { entry: Entry }) {
  const r = entry.response;
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-zinc-800 px-3 py-2 text-sm text-zinc-100">
          <p className="mb-0.5 text-[11px] text-zinc-400">{entry.viewer}</p>
          {entry.message}
        </div>
      </div>
      {entry.error && (
        <p role="alert" className="text-sm text-red-300">
          Could not get a reply: {entry.error}
        </p>
      )}
      {r && (
        <div className="max-w-[90%] rounded-2xl rounded-bl-sm border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
          <p className="mb-1 text-[11px] font-semibold tracking-wide text-emerald-300 uppercase">Sokokali</p>
          <p className="text-sm leading-relaxed text-zinc-100">{r.reply}</p>
          {r.prediction && (
            <div className="mt-3 rounded-lg bg-zinc-950/60 p-3">
              <ProbabilityBar
                home={r.prediction.probabilities.home_win}
                draw={r.prediction.probabilities.draw}
                away={r.prediction.probabilities.away_win}
                homeLabel={r.prediction.home_team}
                awayLabel={r.prediction.away_team}
              />
            </div>
          )}
          {r.forex_signals.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {r.forex_signals.map((s) => (
                <Pill key={s.symbol} tone={DIRECTION_TONE[s.direction]}>
                  {s.display_name} {s.direction.toUpperCase()} · {s.strength}
                </Pill>
              ))}
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Pill tone={r.engine === "llm" ? "info" : "neutral"} title="Which engine wrote this reply">
              {r.engine === "llm" ? "Claude" : "Rule-based"}
            </Pill>
            <Pill>{LANGUAGE_NAMES[r.language]}</Pill>
            <Pill>{humanize(r.intent)}</Pill>
            {r.moderated && <Pill tone="bad">Moderated</Pill>}
            {r.is_simulated_data && <SimulatedTag />}
          </div>
        </div>
      )}
    </div>
  );
}
