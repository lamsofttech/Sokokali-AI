// Basic lip sync driven by word boundaries.
//
// The browser's speech engine does not expose its audio, so the mouth cannot follow
// the waveform. Instead, every time a word starts (the `boundary` event, or the silent
// engine's timer) we walk through that word's letters at speaking pace and shape the
// mouth for each one: open for "a"/"o", wide for "e"/"i", closed for "m"/"b"/"p".

export interface MouthShape {
  /** 0 = closed, 1 = fully open */
  open: number;
  /** 0 = rounded ("o", "u"), 1 = wide ("i", "e") */
  wide: number;
}

const SHAPES: Record<string, MouthShape> = {
  a: { open: 0.9, wide: 0.55 },
  e: { open: 0.55, wide: 0.85 },
  i: { open: 0.35, wide: 0.95 },
  o: { open: 0.8, wide: 0.15 },
  u: { open: 0.45, wide: 0.05 },
  m: { open: 0.02, wide: 0.5 },
  b: { open: 0.02, wide: 0.5 },
  p: { open: 0.02, wide: 0.5 },
  f: { open: 0.15, wide: 0.6 },
  v: { open: 0.15, wide: 0.6 },
  w: { open: 0.3, wide: 0.1 },
};
const CONSONANT: MouthShape = { open: 0.28, wide: 0.5 };
const REST: MouthShape = { open: 0, wide: 0.5 };
export const MS_PER_LETTER = 70;

export function shapeForLetter(letter: string): MouthShape {
  const l = letter.toLowerCase();
  if (SHAPES[l]) return SHAPES[l];
  return /[a-z]/.test(l) ? CONSONANT : REST;
}

/** Rough spoken length of a word, used by the silent engine and the lip-sync timeline. */
export function wordDurationMs(word: string, rate = 1): number {
  const letters = word.replace(/[^\p{L}\p{N}]/gu, "").length;
  return Math.max(160, letters * MS_PER_LETTER) / rate;
}

export function splitWords(text: string): string[] {
  return text.split(/\s+/).filter(Boolean);
}

export class LipSync {
  private word = "";
  private wordStart = 0;
  private speaking = false;
  private sawWords = false;
  private rate = 1;

  setSpeaking(speaking: boolean, now: number): void {
    this.speaking = speaking;
    if (speaking) {
      this.sawWords = false;
      this.wordStart = now;
    } else {
      this.word = "";
    }
  }

  setRate(rate: number): void {
    this.rate = rate > 0 ? rate : 1;
  }

  startWord(word: string, now: number): void {
    this.word = word.replace(/[^\p{L}\p{N}]/gu, "");
    this.wordStart = now;
    this.sawWords = true;
  }

  /** Mouth shape at time `now` (ms, same clock as the other calls). */
  shape(now: number): MouthShape {
    if (!this.speaking) return REST;
    if (!this.sawWords) {
      // Voice without boundary events: a natural-looking talking rhythm instead of a frozen mouth.
      const t = (now - this.wordStart) / 1000;
      return { open: 0.25 + 0.35 * Math.abs(Math.sin(t * 9.5)) * (0.75 + 0.25 * Math.sin(t * 2.3)), wide: 0.5 };
    }
    const elapsed = now - this.wordStart;
    const perLetter = MS_PER_LETTER / this.rate;
    const index = Math.floor(elapsed / perLetter);
    if (!this.word || index >= this.word.length) return { open: 0.06, wide: 0.5 }; // short pause between words
    const target = shapeForLetter(this.word[index] ?? "");
    // Ease in/out within each letter so the mouth doesn't snap.
    const within = (elapsed % perLetter) / perLetter;
    const envelope = 0.6 + 0.4 * Math.sin(Math.PI * within);
    return { open: target.open * envelope, wide: target.wide };
  }
}
