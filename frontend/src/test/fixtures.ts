import type { ChatResponse, ForexSignal, Prediction } from "../services/types";

const freshness = { source: "simulated", is_simulated: true, data_as_of: "2026-10-26T12:00:00Z", age_seconds: 60 };

export const prediction: Prediction = {
  match_id: "sim-epl-f001",
  competition: "Premier League (simulated)",
  home_team: "Arsenal",
  away_team: "Chelsea",
  kickoff: "2026-10-27T16:00:00Z",
  predicted_at: "2026-10-26T12:00:00Z",
  freshness,
  probabilities: { home_win: 0.3303, draw: 0.2612, away_win: 0.4085 },
  expected_goals: { home: 1.29, away: 1.48 },
  model_version: "poisson-elo-blend-0.1.0",
  key_factors: ["Expected goals: Arsenal 1.29 vs Chelsea 1.48"],
  disclaimer: "Probabilities are model estimates, not guaranteed outcomes.",
};

export const signal: ForexSignal = {
  symbol: "EURUSD",
  display_name: "EUR/USD",
  timeframe: "H1",
  generated_at: "2026-10-26T12:00:00Z",
  freshness,
  direction: "sell",
  strength: "medium",
  price: 1.07398,
  trade_levels_enabled: false,
  entry: null,
  stop_loss: null,
  take_profit: null,
  risk_reward: null,
  indicators: { ema_fast: 1.074, ema_slow: 1.075, rsi: 39.5, macd_histogram: -0.0002, atr: 0.0011 },
  key_factors: ["EMA20 below EMA50 (downtrend)"],
  model_version: "fx-technical-0.1.0",
  disclaimer: "Educational technical analysis only, not financial advice.",
};

export const chatReply: ChatResponse = {
  reply: "Wadau! Arsenal dhidi ya Chelsea ni mechi kali sana!",
  language: "sw",
  intent: "prediction",
  teams: ["Arsenal", "Chelsea"],
  prediction,
  currency_pairs: [],
  forex_signals: [],
  is_simulated_data: true,
  moderated: false,
  engine: "llm",
  speech: {
    text: "Wadau! Arsenal dhidi ya Chelsea ni mechi kali sana!",
    voice_languages: ["sw-KE", "sw", "en-KE"],
    animation: "commentary",
    show_simulated_banner: true,
  },
  responded_at: "2026-10-26T12:00:00Z",
};

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
