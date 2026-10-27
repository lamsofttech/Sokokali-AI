// Full-window presenter for going live: capture this window (with its audio) in TikTok LIVE Studio or OBS.
// It follows the live broadcast over the WebSocket and speaks every on-air reply.

import { useCallback, useEffect, useState } from "react";

import { useSpeech } from "../avatar/useSpeech";
import { PresenterStage } from "../components/AvatarPanel";
import { useLiveFeed } from "../hooks/useLiveFeed";
import type { GameUpdate, SayData } from "../services/types";

export const STAGE_CHANNEL = "sokokali-stage";
const TOKEN_KEY = "sokokali.adminToken";

function loadToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function StageView() {
  const speech = useSpeech();
  const { speak, celebrate } = speech;
  const [soundEnabled, setSoundEnabled] = useState(false);
  const portrait = new URLSearchParams(window.location.search).get("layout") === "portrait";

  // Tell open dashboards that a stage is speaking, so they stay quiet (no double audio).
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(STAGE_CHANNEL);
    const beat = () => channel.postMessage({ type: "stage-alive" });
    beat();
    const timer = setInterval(beat, 2000);
    return () => {
      clearInterval(timer);
      channel.close();
    };
  }, []);

  const live = useLiveFeed(loadToken(), {
    onSay: useCallback(
      (say: SayData) => {
        if (say.speech) {
          speak({
            text: say.speech.text,
            languages: say.speech.voice_languages,
            animation: say.speech.animation,
            simulated: say.speech.show_simulated_banner,
          });
        }
      },
      [speak],
    ),
    onGame: useCallback(
      (update: GameUpdate) => {
        if (update.kind === "gift" || update.kind === "milestone") celebrate();
      },
      [celebrate],
    ),
  });

  return (
    <div className="fixed inset-0 bg-black">
      <PresenterStage
        speech={speech}
        outfit={live.gamification?.outfit}
        background={live.gamification?.background}
        full
        portrait={portrait}
      />
      {!soundEnabled && (
        // Browsers only allow speech after a click on the page. This overlay is not visible once clicked.
        <button
          onClick={() => {
            setSoundEnabled(true);
            speech.speak({ text: "Sokokali yuko tayari!", languages: ["sw-KE", "sw", "en-KE"], animation: "celebration", simulated: false });
          }}
          className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/60 text-white"
        >
          <span className="text-2xl font-bold">Click once to enable Sokokali's voice</span>
          <span className="text-sm text-zinc-300">
            Then capture this window in TikTok LIVE Studio (or OBS) with its audio.
            {!live.connected && " Waiting for the live feed..."}
          </span>
        </button>
      )}
    </div>
  );
}
