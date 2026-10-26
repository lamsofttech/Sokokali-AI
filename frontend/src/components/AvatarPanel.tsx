import { Component, type ReactNode, Suspense, lazy, useMemo } from "react";

import type { SpeechController } from "../avatar/useSpeech";
import type { VoiceInfo } from "../avatar/speech";
import { Panel, Pill } from "./ui";

const PresenterScene = lazy(() => import("../avatar/PresenterScene"));

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/** If the 3D scene crashes (driver issues, lost GPU context), show the 2D fallback instead of a blank page. */
class SceneBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function FallbackPresenter({ speaking }: { speaking: boolean }) {
  return (
    <div className="flex h-full items-center justify-center">
      <div
        aria-hidden
        className={`flex size-24 items-center justify-center rounded-full bg-emerald-700 text-3xl font-bold text-white ring-4 ring-red-600 ${speaking ? "animate-pulse" : ""}`}
      >
        SK
      </div>
    </div>
  );
}

const SAMPLE_LINES: Record<string, { text: string; languages: string[] }> = {
  en: { text: "Karibu! I'm Sokokali, your sports and markets presenter.", languages: ["en-KE", "en-GB", "en"] },
  sw: { text: "Karibu sana wadau! Mimi ni Sokokali, mtangazaji wenu wa michezo.", languages: ["sw-KE", "sw", "en-KE"] },
};

export function AvatarPanel({ speech }: { speech: SpeechController }) {
  const hasWebgl = useMemo(webglAvailable, []);
  const { state, settings } = speech;
  const speaking = state.status === "speaking";
  const voices = useMemo(() => sortVoices(speech.voices), [speech.voices]);
  const hasSwahiliVoice = voices.some((v) => v.lang.toLowerCase().startsWith("sw"));

  const voiceStatus = !speech.supported
    ? "This browser has no built-in voice: captions only"
    : !settings.enabled
      ? "Voice muted: captions only"
      : state.engine === "silent" && state.lastError
        ? `Voice unavailable (${state.lastError}): captions only. Click "Test voice" to enable sound.`
        : state.voiceName
          ? `Voice: ${state.voiceName}`
          : "Browser voice ready";

  return (
    <Panel
      title="Avatar & voice"
      subtitle="Live preview of Sokokali presenting"
      actions={
        <Pill tone={speaking ? "ok" : "neutral"}>
          {speaking ? `Speaking${state.queued ? ` · ${state.queued} queued` : ""}` : "Idle"}
        </Pill>
      }
    >
      <div className="relative aspect-video overflow-hidden rounded-lg bg-zinc-950 ring-1 ring-zinc-800">
        {hasWebgl ? (
          <SceneBoundary fallback={<FallbackPresenter speaking={speaking} />}>
            <Suspense fallback={<p className="p-4 text-sm text-zinc-400">Loading presenter...</p>}>
              <PresenterScene animation={speech.animation} lipSync={speech.lipSync} />
            </Suspense>
          </SceneBoundary>
        ) : (
          <FallbackPresenter speaking={speaking} />
        )}
        <div className="pointer-events-none absolute top-2 left-2 flex gap-1.5">
          <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-white">SOKOKALI</span>
          {speech.showSimulatedBanner && (
            <span className="rounded bg-amber-500/90 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-950">
              SIMULATED DATA
            </span>
          )}
        </div>
        {speech.caption && (
          <p
            aria-live="polite"
            className="absolute inset-x-2 bottom-2 rounded-md bg-black/70 px-3 py-1.5 text-center text-sm leading-snug text-white"
          >
            {speech.caption}
          </p>
        )}
      </div>

      <div className="mt-3 space-y-2 text-xs text-zinc-300">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => speech.updateSettings({ enabled: !settings.enabled })}
            aria-pressed={settings.enabled}
            disabled={!speech.supported}
            className="rounded-md border border-zinc-700 px-2.5 py-1 hover:border-emerald-500 disabled:opacity-40"
          >
            {settings.enabled && speech.supported ? "Mute voice" : "Unmute voice"}
          </button>
          <button
            onClick={() => speech.speak({ ...SAMPLE_LINES[hasSwahiliVoice ? "sw" : "en"]!, animation: "celebration", simulated: false })}
            className="rounded-md border border-zinc-700 px-2.5 py-1 hover:border-emerald-500"
          >
            Test voice
          </button>
          <button onClick={speech.celebrate} className="rounded-md border border-zinc-700 px-2.5 py-1 hover:border-emerald-500">
            Celebrate
          </button>
          <button
            onClick={speech.skip}
            disabled={!speaking}
            className="rounded-md border border-zinc-700 px-2.5 py-1 hover:border-emerald-500 disabled:opacity-40"
          >
            Skip
          </button>
          <button
            onClick={speech.stop}
            disabled={!speaking}
            className="rounded-md border border-zinc-700 px-2.5 py-1 hover:border-red-500 disabled:opacity-40"
          >
            Stop
          </button>
        </div>
        {speech.supported && (
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex min-w-0 items-center gap-1.5">
              Voice
              <select
                value={settings.voiceURI}
                onChange={(e) => speech.updateSettings({ voiceURI: e.target.value })}
                className="max-w-56 min-w-0 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-100"
              >
                <option value="">Automatic (match reply language)</option>
                {voices.map((v) => (
                  <option key={v.voiceURI} value={v.voiceURI}>
                    {v.name} ({v.lang})
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1.5">
              Speed
              <input
                type="range"
                min={0.7}
                max={1.4}
                step={0.05}
                value={settings.rate}
                onChange={(e) => speech.updateSettings({ rate: Number(e.target.value) })}
                aria-valuetext={`${settings.rate.toFixed(2)}x`}
              />
              <span className="tabular-nums">{settings.rate.toFixed(2)}x</span>
            </label>
          </div>
        )}
        <p className="text-zinc-400">{voiceStatus}</p>
        {speech.supported && voices.length > 0 && !hasSwahiliVoice && (
          <p className="text-amber-300/90">
            No Kiswahili voice installed in this browser, so Kiswahili replies use an English voice. Microsoft Edge on
            Windows usually offers Kiswahili (Kenya) voices.
          </p>
        )}
      </div>
    </Panel>
  );
}

/** Kenyan English and Kiswahili voices first, then other English, then the rest. */
function sortVoices(voices: VoiceInfo[]): VoiceInfo[] {
  const rank = (v: VoiceInfo) => {
    const lang = v.lang.toLowerCase();
    if (lang.startsWith("sw")) return 0;
    if (lang === "en-ke") return 1;
    if (lang.startsWith("en")) return 2;
    return 3;
  };
  return [...voices].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
}
