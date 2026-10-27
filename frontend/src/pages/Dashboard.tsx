import { useCallback, useEffect, useRef, useState } from "react";

import { useSpeech } from "../avatar/useSpeech";
import { AvatarPanel } from "../components/AvatarPanel";
import { BroadcastPanel } from "../components/BroadcastPanel";
import { GamificationPanel } from "../components/GamificationPanel";
import { LiveFeedPanel } from "../components/LiveFeedPanel";
import { RelayPanel } from "../components/RelayPanel";
import { STAGE_CHANNEL } from "./StageView";

import { ChatPanel } from "../components/ChatPanel";
import { ComingNextPanel } from "../components/ComingNextPanel";
import { ErrorLogPanel } from "../components/ErrorLogPanel";
import { FixturesPanel } from "../components/FixturesPanel";
import { ForexPanel } from "../components/ForexPanel";
import { ModelPanel } from "../components/ModelPanel";
import { StatusPanel } from "../components/StatusPanel";
import { Pill } from "../components/ui";
import { usePolling } from "../hooks/usePolling";
import { useLiveFeed } from "../hooks/useLiveFeed";
import { useRequestLog } from "../hooks/useRequestLog";
import type { SokokaliApi } from "../services/api";
import type { ChatResponse, GameUpdate, GamificationStatus, SayData } from "../services/types";

const TOKEN_KEY = "sokokali.adminToken";

function loadToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function Dashboard({ client }: { client: SokokaliApi }) {
  const fetchStatus = useCallback(() => client.status(), [client]);
  const status = usePolling(fetchStatus, 10_000);
  const events = useRequestLog(client);
  const speech = useSpeech();
  const { speak, celebrate } = speech;
  const [adminToken, setAdminToken] = useState(loadToken);
  useEffect(() => {
    client.adminToken = adminToken;
  }, [client, adminToken]);
  const saveToken = useCallback((token: string) => {
    setAdminToken(token);
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      // storage blocked: token lasts for this session only
    }
  }, []);

  // When a stage view (window captured for TikTok) is open, it does the talking; the dashboard stays quiet.
  const stageSeenAt = useRef(0);
  const [stageOpen, setStageOpen] = useState(false);
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(STAGE_CHANNEL);
    channel.onmessage = () => {
      stageSeenAt.current = Date.now();
      setStageOpen(true);
    };
    const timer = setInterval(() => setStageOpen(Date.now() - stageSeenAt.current < 5000), 2500);
    return () => {
      clearInterval(timer);
      channel.close();
    };
  }, []);

  const gamificationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const setGamificationRef = useRef<(g: GamificationStatus) => void>(() => undefined);
  const live = useLiveFeed(adminToken, {
    onSay: useCallback(
      (say: SayData) => {
        if (say.speech && Date.now() - stageSeenAt.current > 5000) {
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
        // Gifts and milestones get a visual celebration only; they never jump the answer queue.
        if (update.kind === "gift" || update.kind === "milestone") celebrate();
      },
      [celebrate],
    ),
    onGamificationChanged: useCallback(() => {
      if (gamificationTimer.current) return; // at most one refresh per second
      gamificationTimer.current = setTimeout(() => {
        gamificationTimer.current = null;
        client.gamification().then((g) => setGamificationRef.current(g), () => undefined);
      }, 1000);
    }, [client]),
  });
  setGamificationRef.current = live.setGamification;
  useEffect(() => () => {
    if (gamificationTimer.current) clearTimeout(gamificationTimer.current);
  }, []);
  const refreshStatus = status.refresh;
  const onReply = useCallback(
    (reply: ChatResponse) => {
      refreshStatus();
      if (reply.speech) {
        speak({
          text: reply.speech.text,
          languages: reply.speech.voice_languages,
          animation: reply.speech.animation,
          simulated: reply.speech.show_simulated_banner,
        });
      }
    },
    [refreshStatus, speak],
  );

  const online = status.data !== null && status.error === null;
  const ai = status.data?.components.find((c) => c.name === "ai_engine");
  const usingClaude = ai?.detail.startsWith("Claude") && ai.status === "ok";

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <img src="/favicon.svg" alt="" className="size-8" />
            <div>
              <h1 className="text-lg leading-tight font-bold">Sokokali</h1>
              <p className="text-xs text-zinc-400">AI sports &amp; markets presenter · admin dashboard</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={online ? "ok" : status.loading ? "neutral" : "bad"}>
              <span className={`size-1.5 rounded-full ${online ? "bg-emerald-400" : "bg-red-400"}`} />
              {online ? "Online" : status.loading ? "Connecting..." : "Offline"}
            </Pill>
            {ai && (
              <Pill tone={usingClaude ? "info" : ai.status === "degraded" ? "warn" : "neutral"} title={ai.detail}>
                AI: {usingClaude ? "Claude" : ai.status === "degraded" ? "Claude paused (rule-based)" : "Rule-based"}
              </Pill>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-4 px-4 py-4 sm:px-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <BroadcastPanel
            client={client}
            state={live.state}
            connected={live.connected}
            authError={live.authError}
            token={adminToken}
            onTokenChange={saveToken}
          />
          <RelayPanel client={client} active={live.state?.audience === "relay"} />
          <LiveFeedPanel feed={live.feed} simulated={live.state?.source_is_simulated ?? false} />
          <ChatPanel client={client} onReply={onReply} />
          <FixturesPanel client={client} />
          <ModelPanel client={client} />
        </div>
        <div className="space-y-4">
          {stageOpen && (
            <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
              Stage view is open: it speaks the broadcast, so this dashboard stays quiet.
            </p>
          )}
          <AvatarPanel speech={speech} outfit={live.gamification?.outfit} background={live.gamification?.background} />
          <GamificationPanel status={live.gamification} />
          <StatusPanel status={status} events={events} />
          <ForexPanel client={client} />
          <ErrorLogPanel events={events} />
          <ComingNextPanel />
        </div>
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-6 text-[11px] text-zinc-500 sm:px-6">
        Predictions and signals are model estimates, not guarantees, and are not betting or financial advice.
      </footer>
    </div>
  );
}
