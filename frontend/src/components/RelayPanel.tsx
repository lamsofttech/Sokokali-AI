import { type FormEvent, useRef, useState } from "react";

import type { SokokaliApi } from "../services/api";
import { humanize } from "../services/format";
import type { RelayRequest, RelayResult } from "../services/types";
import { ErrorNote, Panel, Pill } from "./ui";

interface Sent {
  id: number;
  label: string;
  result?: RelayResult;
  error?: string;
}

type Kind = "comment" | "gift" | "join" | "follow";

/** Parse "username: message" lines (pasted from TikTok LIVE comments). Lines without a colon are skipped. */
export function parseBulk(text: string): RelayRequest[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line) => {
      const i = line.indexOf(":");
      if (i <= 0) return [];
      const viewer_name = line.slice(0, i).trim().replace(/^@/, "");
      const message = line.slice(i + 1).trim();
      return viewer_name && message ? [{ viewer_name, text: message, kind: "comment" as const }] : [];
    });
}

export function RelayPanel({ client, active }: { client: SokokaliApi; active: boolean }) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [kind, setKind] = useState<Kind>("comment");
  const [gift, setGift] = useState("Rose");
  const [bulk, setBulk] = useState("");
  const [sent, setSent] = useState<Sent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const nextId = useRef(1);
  const messageRef = useRef<HTMLInputElement>(null);

  async function relay(event: RelayRequest, label: string) {
    const id = nextId.current++;
    setSent((prev) => [{ id, label }, ...prev].slice(0, 12));
    try {
      const result = await client.relay(event);
      setSent((prev) => prev.map((s) => (s.id === id ? { ...s, result } : s)));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setSent((prev) => prev.map((s) => (s.id === id ? { ...s, error: message } : s)));
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const viewer = name.trim().replace(/^@/, "");
    if (!viewer) return setError("Enter the TikTok username.");
    if (kind === "comment" && !text.trim()) return setError("Enter the comment.");
    const event: RelayRequest =
      kind === "comment"
        ? { viewer_name: viewer, kind, text: text.trim() }
        : kind === "gift"
          ? { viewer_name: viewer, kind, gift_name: gift.trim() || "gift" }
          : { viewer_name: viewer, kind };
    void relay(event, kind === "comment" ? `${viewer}: ${text.trim()}` : `${viewer} · ${kind}${kind === "gift" ? ` (${gift})` : ""}`);
    setText("");
    messageRef.current?.focus();
  }

  async function sendBulk() {
    const events = parseBulk(bulk);
    if (events.length === 0) return setError('Paste lines like "username: comment".');
    setError(null);
    setBulk("");
    for (const event of events) await relay(event, `${event.viewer_name}: ${event.text}`);
  }

  return (
    <Panel
      title="Moderator relay (TikTok LIVE)"
      subtitle="Copy viewers' comments from TikTok here; Sokokali answers them on air"
      actions={<Pill tone={active ? "ok" : "warn"}>{active ? "Relay audience on" : "Choose the relay audience"}</Pill>}
    >
      <div className="space-y-3 text-sm">
        {!active && (
          <p className="text-xs text-amber-200/90">
            Stop the show, choose "TikTok LIVE via moderator relay" as the audience, then Start. Relayed comments are still
            accepted otherwise, but simulated viewers would be mixed in.
          </p>
        )}
        <form onSubmit={onSubmit} className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <label className="sr-only" htmlFor="relay-name">
              TikTok username
            </label>
            <input
              id="relay-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={50}
              placeholder="@username"
              className="w-36 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-100 focus:border-emerald-500 focus:outline-none"
            />
            <label className="sr-only" htmlFor="relay-kind">
              Event type
            </label>
            <select
              id="relay-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as Kind)}
              className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-2 text-zinc-100"
            >
              <option value="comment">Comment</option>
              <option value="gift">Gift</option>
              <option value="join">Joined</option>
              <option value="follow">Followed</option>
            </select>
            {kind === "comment" && (
              <>
                <label className="sr-only" htmlFor="relay-text">
                  Comment
                </label>
                <input
                  id="relay-text"
                  ref={messageRef}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  maxLength={500}
                  placeholder="Their comment, exactly as written"
                  className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-100 focus:border-emerald-500 focus:outline-none"
                />
              </>
            )}
            {kind === "gift" && (
              <>
                <label className="sr-only" htmlFor="relay-gift">
                  Gift name
                </label>
                <input
                  id="relay-gift"
                  value={gift}
                  onChange={(e) => setGift(e.target.value)}
                  maxLength={50}
                  className="w-32 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-100"
                />
              </>
            )}
            <button
              type="submit"
              className="rounded-lg bg-emerald-600 px-4 py-2 font-semibold text-white hover:bg-emerald-500"
            >
              Relay
            </button>
          </div>
        </form>

        <details className="rounded-lg border border-zinc-800 p-2">
          <summary className="cursor-pointer text-xs text-zinc-300">Paste several comments at once</summary>
          <label className="sr-only" htmlFor="relay-bulk">
            Comments, one per line
          </label>
          <textarea
            id="relay-bulk"
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
            rows={4}
            placeholder={"wanjiku_254: Arsenal vs Chelsea nani atashinda?\nbrian.ke: EUR/USD signal leo?"}
            className="mt-2 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 font-mono text-xs text-zinc-100"
          />
          <button
            type="button"
            onClick={() => void sendBulk()}
            className="mt-1 rounded border border-zinc-700 px-2 py-1 text-xs hover:border-emerald-500"
          >
            Relay all
          </button>
        </details>

        {error && <ErrorNote message={error} />}

        {sent.length > 0 && (
          <ul className="space-y-1 text-xs" aria-live="polite">
            {sent.map((s) => (
              <li key={s.id} className="flex items-start justify-between gap-2">
                <span className="min-w-0 truncate text-zinc-300">{s.label}</span>
                {s.error ? (
                  <Pill tone="bad">{s.error}</Pill>
                ) : !s.result ? (
                  <Pill>sending...</Pill>
                ) : s.result.accepted ? (
                  <Pill tone="info">queued · priority {s.result.priority}</Pill>
                ) : s.result.reason ? (
                  <Pill tone={s.result.reason === "moderated" ? "bad" : "neutral"}>{humanize(s.result.reason)}</Pill>
                ) : (
                  <Pill tone="ok">received</Pill>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}
