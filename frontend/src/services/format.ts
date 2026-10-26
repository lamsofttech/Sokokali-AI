import type { Language } from "./types";

export const LANGUAGE_NAMES: Record<Language, string> = {
  en: "English",
  sw: "Kiswahili",
  sheng: "Sheng",
};

export function percent(probability: number): string {
  return `${Math.round(probability * 100)}%`;
}

export function kickoff(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function clock(date: Date): string {
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function duration(seconds: number): string {
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

export function humanize(value: string): string {
  return value.replace(/_/g, " ");
}
