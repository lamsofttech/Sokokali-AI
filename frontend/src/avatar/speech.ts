// Text-to-speech for the avatar.
//
// BrowserSpeechEngine uses the free Web Speech API built into the browser.
// SilentSpeechEngine is the graceful fallback: no audio, but it walks through the
// words at speaking pace so captions, lip sync and animations still work.
// SpeechQueue plays one reply at a time so Sokokali never talks over itself.

import { splitWords, wordDurationMs } from "./lipSync";

export type AvatarAnimation = "idle" | "speaking" | "commentary" | "celebration";

export interface SpeakRequest {
  text: string;
  /** BCP 47 languages to try, best first, e.g. ["sw-KE", "sw", "en-KE"] */
  languages: string[];
  voiceURI?: string;
  rate?: number;
  pitch?: number;
}

export interface SpeakCallbacks {
  onStart: (voiceName: string | null) => void;
  onWord: (word: string) => void;
  onEnd: () => void;
  onError: (reason: string) => void;
}

export interface SpeechEngine {
  readonly kind: "browser" | "silent";
  speak(request: SpeakRequest, callbacks: SpeakCallbacks): void;
  cancel(): void;
}

/** The voice fields we use; a subset of SpeechSynthesisVoice so tests can pass plain objects. */
export interface VoiceInfo {
  name: string;
  lang: string;
  voiceURI: string;
  localService?: boolean;
}

/** Best voice for the requested languages: exact tag, then same base language, then the browser default. */
export function pickVoice<V extends VoiceInfo>(voices: V[], languages: string[], preferredURI?: string): V | null {
  if (preferredURI) {
    const preferred = voices.find((v) => v.voiceURI === preferredURI);
    if (preferred) return preferred;
  }
  const norm = (tag: string) => tag.replace("_", "-").toLowerCase();
  for (const lang of languages.map(norm)) {
    const exact = voices.find((v) => norm(v.lang) === lang);
    if (exact) return exact;
    const base = lang.split("-")[0];
    const sameBase = voices.find((v) => norm(v.lang).split("-")[0] === base);
    if (sameBase) return sameBase;
  }
  return null;
}

export function browserSpeechSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

export class BrowserSpeechEngine implements SpeechEngine {
  readonly kind = "browser";
  private watchdog: ReturnType<typeof setTimeout> | null = null;

  voices(): SpeechSynthesisVoice[] {
    return window.speechSynthesis.getVoices();
  }

  speak(request: SpeakRequest, cb: SpeakCallbacks): void {
    const synth = window.speechSynthesis;
    const utterance = new SpeechSynthesisUtterance(request.text);
    const voice = pickVoice(this.voices(), request.languages, request.voiceURI);
    if (voice) utterance.voice = voice;
    utterance.lang = voice?.lang ?? request.languages[0] ?? "en";
    utterance.rate = request.rate ?? 1;
    utterance.pitch = request.pitch ?? 1;

    let finished = false;
    const finish = (error?: string) => {
      if (finished) return;
      finished = true;
      if (this.watchdog) clearTimeout(this.watchdog);
      if (error) cb.onError(error);
      else cb.onEnd();
    };
    utterance.onstart = () => cb.onStart(voice?.name ?? null);
    utterance.onboundary = (event) => {
      if (event.name && event.name !== "word") return;
      const rest = request.text.slice(event.charIndex);
      const word = event.charLength ? rest.slice(0, event.charLength) : (rest.match(/^\S+/)?.[0] ?? "");
      if (word) cb.onWord(word);
    };
    utterance.onend = () => finish();
    utterance.onerror = (event) => finish(event.error === "interrupted" || event.error === "canceled" ? undefined : event.error);

    // Some browsers occasionally never fire `end`; don't let the queue stall forever.
    const expected = splitWords(request.text).reduce((ms, w) => ms + wordDurationMs(w, utterance.rate) + 120, 0);
    this.watchdog = setTimeout(() => {
      synth.cancel();
      finish();
    }, expected * 2 + 5000);

    synth.speak(utterance);
  }

  cancel(): void {
    if (this.watchdog) clearTimeout(this.watchdog);
    window.speechSynthesis.cancel();
  }
}

export class SilentSpeechEngine implements SpeechEngine {
  readonly kind = "silent";
  private timers: ReturnType<typeof setTimeout>[] = [];
  private cancelCurrent: (() => void) | null = null;

  speak(request: SpeakRequest, cb: SpeakCallbacks): void {
    this.cancel();
    const rate = request.rate ?? 1;
    let at = 0;
    cb.onStart(null);
    for (const word of splitWords(request.text)) {
      this.timers.push(setTimeout(() => cb.onWord(word), at));
      at += wordDurationMs(word, rate) + 120 / rate;
    }
    this.timers.push(setTimeout(() => cb.onEnd(), at));
    this.cancelCurrent = cb.onEnd;
  }

  cancel(): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
    const end = this.cancelCurrent;
    this.cancelCurrent = null;
    end?.();
  }
}

export interface SpeechItem {
  id: number;
  text: string;
  languages: string[];
  animation: AvatarAnimation;
  simulated: boolean;
}

export interface QueueState {
  status: "idle" | "speaking";
  current: SpeechItem | null;
  queued: number;
  engine: "browser" | "silent";
  voiceName: string | null;
  lastError: string | null;
}

type StateListener = (state: QueueState) => void;
type WordListener = (word: string) => void;

export class SpeechQueue {
  private engine: SpeechEngine;
  private readonly fallback: SpeechEngine;
  private items: SpeechItem[] = [];
  private state: QueueState;
  private readonly stateListeners = new Set<StateListener>();
  private readonly wordListeners = new Set<WordListener>();
  private settings: { voiceURI?: string; rate: number; pitch: number } = { rate: 1, pitch: 1 };
  private playing = 0; // token of the item being spoken, so stale callbacks are ignored

  constructor(
    engine: SpeechEngine,
    fallback: SpeechEngine = new SilentSpeechEngine(),
    private readonly maxQueued = 5,
  ) {
    this.engine = engine;
    this.fallback = fallback;
    this.state = { status: "idle", current: null, queued: 0, engine: engine.kind, voiceName: null, lastError: null };
  }

  getState(): QueueState {
    return this.state;
  }

  subscribe(listener: StateListener): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  onWord(listener: WordListener): () => void {
    this.wordListeners.add(listener);
    return () => this.wordListeners.delete(listener);
  }

  /** Switches engine (e.g. voice muted -> silent); the current reply restarts on the new engine. */
  setEngine(engine: SpeechEngine): void {
    this.stopEngines();
    this.engine = engine;
    this.update({ engine: engine.kind, voiceName: null, lastError: null });
    if (this.state.current) this.play(this.state.current, engine);
  }

  configure(settings: Partial<{ voiceURI: string | undefined; rate: number; pitch: number }>): void {
    this.settings = { ...this.settings, ...settings };
  }

  /** Adds a reply to the queue. When the queue is full the oldest waiting reply is dropped. */
  enqueue(item: SpeechItem): void {
    this.items.push(item);
    while (this.items.length > this.maxQueued) this.items.shift();
    this.update({ queued: this.items.length });
    if (this.state.status === "idle") this.next();
  }

  /** Stops the current reply and moves on to the next one. */
  skip(): void {
    this.stopEngines();
    this.next();
  }

  private stopEngines(): void {
    this.playing++; // invalidate callbacks from whatever was playing
    this.engine.cancel();
    if (this.fallback !== this.engine) this.fallback.cancel();
  }

  /** Stops speaking and drops everything waiting. */
  clear(): void {
    this.items = [];
    this.skip();
  }

  private next(): void {
    const item = this.items.shift();
    if (!item) {
      this.update({ status: "idle", current: null, queued: 0 });
      return;
    }
    this.update({ status: "speaking", current: item, queued: this.items.length });
    this.play(item, this.engine);
  }

  private play(item: SpeechItem, engine: SpeechEngine): void {
    const token = ++this.playing;
    const live = () => token === this.playing;
    engine.speak(
      { text: item.text, languages: item.languages, ...this.settings },
      {
        onStart: (voiceName) => live() && this.update({ engine: engine.kind, voiceName }),
        onWord: (word) => live() && this.wordListeners.forEach((l) => l(word)),
        onEnd: () => live() && this.next(),
        onError: (reason) => {
          if (!live()) return;
          // e.g. "not-allowed" before the user has interacted with the page: keep the show going silently.
          this.update({ lastError: reason });
          if (engine !== this.fallback) this.play(item, this.fallback);
          else this.next();
        },
      },
    );
  }

  private update(patch: Partial<QueueState>): void {
    this.state = { ...this.state, ...patch };
    this.stateListeners.forEach((l) => l(this.state));
  }
}
