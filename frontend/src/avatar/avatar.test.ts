import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LipSync, MS_PER_LETTER, shapeForLetter, wordDurationMs } from "./lipSync";
import {
  type QueueState,
  type SpeakCallbacks,
  type SpeakRequest,
  type SpeechEngine,
  SilentSpeechEngine,
  SpeechQueue,
  pickVoice,
} from "./speech";

describe("lip sync", () => {
  it("shapes the mouth per letter", () => {
    expect(shapeForLetter("a").open).toBeGreaterThan(shapeForLetter("m").open);
    expect(shapeForLetter("i").wide).toBeGreaterThan(shapeForLetter("o").wide);
    expect(shapeForLetter("?").open).toBe(0);
  });

  it("is closed when not speaking and follows the current word", () => {
    const lip = new LipSync();
    expect(lip.shape(0).open).toBe(0);
    lip.setSpeaking(true, 0);
    lip.startWord("Mama", 1000);
    const m = lip.shape(1000 + MS_PER_LETTER * 0.5).open; // middle of "M"
    const a = lip.shape(1000 + MS_PER_LETTER * 1.5).open; // middle of "a"
    expect(a).toBeGreaterThan(m);
    expect(lip.shape(1000 + MS_PER_LETTER * 10).open).toBeLessThan(0.1); // pause after the word
    lip.setSpeaking(false, 2000);
    expect(lip.shape(2000).open).toBe(0);
  });

  it("keeps talking without boundary events", () => {
    const lip = new LipSync();
    lip.setSpeaking(true, 0);
    const opens = [50, 100, 150, 200].map((t) => lip.shape(t).open);
    expect(Math.max(...opens)).toBeGreaterThan(0.3);
  });

  it("estimates word duration from letters and rate", () => {
    expect(wordDurationMs("Sokokali")).toBe(8 * MS_PER_LETTER);
    expect(wordDurationMs("Sokokali", 2)).toBe(4 * MS_PER_LETTER);
    expect(wordDurationMs("a")).toBe(160);
  });
});

describe("pickVoice", () => {
  const voices = [
    { name: "David", lang: "en-US", voiceURI: "david" },
    { name: "Zuri", lang: "sw-KE", voiceURI: "zuri" },
    { name: "Hazel", lang: "en_GB", voiceURI: "hazel" },
  ];

  it("prefers an exact language, then the same base language", () => {
    expect(pickVoice(voices, ["sw-KE", "en-KE"])?.name).toBe("Zuri");
    expect(pickVoice(voices, ["en-GB"])?.name).toBe("Hazel");
    expect(pickVoice(voices, ["en-KE"])?.name).toBe("David");
    expect(pickVoice(voices, ["fr-FR"])).toBeNull();
  });

  it("honours an explicitly chosen voice", () => {
    expect(pickVoice(voices, ["sw-KE"], "hazel")?.name).toBe("Hazel");
    expect(pickVoice(voices, ["sw-KE"], "missing")?.name).toBe("Zuri");
  });
});

/** Engine whose utterances finish only when the test says so. */
class ManualEngine implements SpeechEngine {
  readonly kind = "browser";
  spoken: SpeakRequest[] = [];
  callbacks: SpeakCallbacks[] = [];
  cancels = 0;
  speak(request: SpeakRequest, callbacks: SpeakCallbacks): void {
    this.spoken.push(request);
    this.callbacks.push(callbacks);
  }
  cancel(): void {
    this.cancels++;
  }
  last(): SpeakCallbacks {
    return this.callbacks[this.callbacks.length - 1]!;
  }
}

const item = (id: number, text = `reply ${id}`) => ({
  id,
  text,
  languages: ["en-KE"],
  animation: "speaking" as const,
  simulated: false,
});

describe("SpeechQueue", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("speaks one reply at a time, in order", () => {
    const engine = new ManualEngine();
    const queue = new SpeechQueue(engine);
    queue.enqueue(item(1));
    queue.enqueue(item(2));
    expect(engine.spoken.map((s) => s.text)).toEqual(["reply 1"]);
    expect(queue.getState()).toMatchObject({ status: "speaking", queued: 1 });

    engine.last().onEnd();
    expect(engine.spoken.map((s) => s.text)).toEqual(["reply 1", "reply 2"]);
    engine.last().onEnd();
    expect(queue.getState()).toMatchObject({ status: "idle", current: null, queued: 0 });
  });

  it("drops the oldest waiting reply when the queue is full", () => {
    const engine = new ManualEngine();
    const queue = new SpeechQueue(engine, new SilentSpeechEngine(), 2);
    [1, 2, 3, 4].forEach((n) => queue.enqueue(item(n)));
    engine.last().onEnd();
    expect(engine.spoken.map((s) => s.text)).toEqual(["reply 1", "reply 3"]);
  });

  it("skip and clear stop the current reply", () => {
    const engine = new ManualEngine();
    const queue = new SpeechQueue(engine);
    queue.enqueue(item(1));
    queue.enqueue(item(2));
    queue.skip();
    expect(engine.cancels).toBeGreaterThan(0);
    expect(queue.getState().current?.id).toBe(2);
    queue.clear();
    expect(queue.getState().status).toBe("idle");
    engine.callbacks[0]!.onEnd(); // late callback from the cancelled reply is ignored
    expect(queue.getState().status).toBe("idle");
  });

  it("falls back to the silent engine when the voice fails", () => {
    const engine = new ManualEngine();
    const queue = new SpeechQueue(engine);
    const states: QueueState[] = [];
    queue.subscribe((s) => states.push(s));
    queue.enqueue(item(1, "Karibu wadau"));
    engine.last().onError("not-allowed");
    expect(queue.getState()).toMatchObject({ engine: "silent", lastError: "not-allowed", status: "speaking" });
    vi.runAllTimers();
    expect(queue.getState().status).toBe("idle");
  });

  it("forwards word events for lip sync and passes voice settings", () => {
    const engine = new ManualEngine();
    const queue = new SpeechQueue(engine);
    const words: string[] = [];
    queue.onWord((w) => words.push(w));
    queue.configure({ voiceURI: "zuri", rate: 1.2 });
    queue.enqueue(item(1));
    engine.last().onStart("Zuri");
    engine.last().onWord("reply");
    expect(words).toEqual(["reply"]);
    expect(engine.spoken[0]).toMatchObject({ voiceURI: "zuri", rate: 1.2 });
    expect(queue.getState().voiceName).toBe("Zuri");
  });

  it("silent engine emits every word, then ends", () => {
    const silent = new SilentSpeechEngine();
    const words: string[] = [];
    const onEnd = vi.fn();
    silent.speak({ text: "Wasee itakuwa moto", languages: ["sw"] }, { onStart: vi.fn(), onWord: (w) => words.push(w), onEnd, onError: vi.fn() });
    vi.runAllTimers();
    expect(words).toEqual(["Wasee", "itakuwa", "moto"]);
    expect(onEnd).toHaveBeenCalledOnce();
  });
});
