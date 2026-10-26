import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LipSync } from "./lipSync";
import {
  type AvatarAnimation,
  BrowserSpeechEngine,
  type QueueState,
  SilentSpeechEngine,
  type SpeechItem,
  SpeechQueue,
  type VoiceInfo,
  browserSpeechSupported,
} from "./speech";

export interface VoiceSettings {
  /** false = muted: the avatar still "speaks" with captions, but no audio */
  enabled: boolean;
  /** "" = pick automatically from the reply's language */
  voiceURI: string;
  rate: number;
}

const STORAGE_KEY = "sokokali.voice";
const DEFAULTS: VoiceSettings = { enabled: true, voiceURI: "", rate: 1 };
const CELEBRATION_MS = 2500;

function loadSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<VoiceSettings>) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

function saveSettings(settings: VoiceSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // Private mode or blocked storage: settings just won't persist.
  }
}

export interface SpeechController {
  supported: boolean;
  state: QueueState;
  settings: VoiceSettings;
  voices: VoiceInfo[];
  lipSync: LipSync;
  /** The animation the avatar should play right now */
  animation: AvatarAnimation;
  /** Caption for the reply being spoken */
  caption: string | null;
  showSimulatedBanner: boolean;
  speak: (item: Omit<SpeechItem, "id">) => void;
  skip: () => void;
  stop: () => void;
  celebrate: () => void;
  updateSettings: (patch: Partial<VoiceSettings>) => void;
}

export function useSpeech(): SpeechController {
  const supported = browserSpeechSupported();
  const browserEngine = useMemo(() => (supported ? new BrowserSpeechEngine() : null), [supported]);
  const silentEngine = useMemo(() => new SilentSpeechEngine(), []);
  const [settings, setSettings] = useState<VoiceSettings>(loadSettings);
  // Created once with the silent engine; the effect below switches to the browser voice when enabled.
  const queue = useMemo(() => new SpeechQueue(silentEngine, silentEngine), [silentEngine]);
  const lipSync = useMemo(() => new LipSync(), []);
  const [state, setState] = useState<QueueState>(queue.getState());
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [celebrating, setCelebrating] = useState(false);
  const celebrationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nextId = useRef(1);

  useEffect(() => queue.subscribe(setState), [queue]);
  useEffect(() => queue.onWord((word) => lipSync.startWord(word, performance.now())), [queue, lipSync]);
  useEffect(() => lipSync.setSpeaking(state.status === "speaking", performance.now()), [lipSync, state.status]);

  // Voices load asynchronously in most browsers.
  useEffect(() => {
    if (!browserEngine) return;
    const load = () => setVoices(browserEngine.voices().map(({ name, lang, voiceURI, localService }) => ({ name, lang, voiceURI, localService })));
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, [browserEngine]);

  useEffect(() => {
    queue.configure({ voiceURI: settings.voiceURI || undefined, rate: settings.rate });
    lipSync.setRate(settings.rate);
  }, [queue, lipSync, settings.voiceURI, settings.rate]);

  const wantBrowser = settings.enabled && browserEngine !== null;
  useEffect(() => {
    const engine = wantBrowser && browserEngine ? browserEngine : silentEngine;
    if (queue.getState().engine !== engine.kind) queue.setEngine(engine);
  }, [queue, wantBrowser, browserEngine, silentEngine]);

  // Stop talking when the dashboard unmounts.
  useEffect(() => () => queue.clear(), [queue]);

  const updateSettings = useCallback((patch: Partial<VoiceSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      saveSettings(next);
      return next;
    });
  }, []);

  const speak = useCallback(
    (item: Omit<SpeechItem, "id">) => {
      if (item.text.trim()) queue.enqueue({ ...item, id: nextId.current++ });
    },
    [queue],
  );

  const celebrate = useCallback(() => {
    if (celebrationTimer.current) clearTimeout(celebrationTimer.current);
    setCelebrating(true);
    celebrationTimer.current = setTimeout(() => setCelebrating(false), CELEBRATION_MS);
  }, []);

  useEffect(() => () => {
    if (celebrationTimer.current) clearTimeout(celebrationTimer.current);
  }, []);

  const current = state.current;
  const animation: AvatarAnimation = celebrating
    ? "celebration"
    : current
      ? current.animation === "idle"
        ? "speaking"
        : current.animation
      : "idle";

  return {
    supported,
    state,
    settings,
    voices,
    lipSync,
    animation,
    caption: current?.text ?? null,
    showSimulatedBanner: current?.simulated ?? false,
    speak,
    skip: useCallback(() => queue.skip(), [queue]),
    stop: useCallback(() => queue.clear(), [queue]),
    celebrate,
    updateSettings,
  };
}
