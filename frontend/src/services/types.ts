// TypeScript mirrors of the backend's Pydantic schemas (backend/app/schemas).

export type Language = "en" | "sw" | "sheng";

export type Intent =
  | "greeting"
  | "prediction"
  | "fixtures"
  | "results"
  | "team_form"
  | "forex"
  | "guarantee_request"
  | "help"
  | "moderated"
  | "unknown";

export interface DataFreshness {
  source: string;
  is_simulated: boolean;
  data_as_of: string;
  age_seconds: number;
}

export interface Team {
  team_id: string;
  name: string;
  competition: string;
  aliases: string[];
}

export interface Fixture {
  match_id: string;
  competition: string;
  home_team: Team;
  away_team: Team;
  kickoff: string;
  status: "scheduled" | "live" | "finished";
}

export interface FixtureList {
  fixtures: Fixture[];
  freshness: DataFreshness;
}

export interface Prediction {
  match_id: string;
  competition: string;
  home_team: string;
  away_team: string;
  kickoff: string;
  predicted_at: string;
  freshness: DataFreshness;
  probabilities: { home_win: number; draw: number; away_win: number };
  expected_goals: { home: number; away: number };
  model_version: string;
  key_factors: string[];
  disclaimer: string;
}

export type SignalDirection = "buy" | "sell" | "neutral";
export type SignalStrength = "low" | "medium" | "high";

export interface ForexSignal {
  symbol: string;
  display_name: string;
  timeframe: string;
  generated_at: string;
  freshness: DataFreshness;
  direction: SignalDirection;
  strength: SignalStrength;
  price: number;
  trade_levels_enabled: boolean;
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  indicators: { ema_fast: number; ema_slow: number; rsi: number; macd_histogram: number; atr: number };
  key_factors: string[];
  model_version: string;
  disclaimer: string;
}

export interface ForexSignalList {
  signals: ForexSignal[];
}

export interface ChatRequest {
  message: string;
  viewer_id?: string;
  language?: Language;
}

export interface SpeechCue {
  text: string;
  voice_languages: string[];
  animation: "idle" | "speaking" | "commentary" | "celebration";
  show_simulated_banner: boolean;
}

export interface ChatResponse {
  reply: string;
  language: Language;
  intent: Intent;
  teams: string[];
  prediction: Prediction | null;
  currency_pairs: string[];
  forex_signals: ForexSignal[];
  is_simulated_data: boolean;
  moderated: boolean;
  engine: "llm" | "rules";
  speech: SpeechCue | null;
  responded_at: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface ComponentStatus {
  name: string;
  status: string;
  detail: string;
}

export interface StatusResponse {
  service: string;
  version: string;
  environment: string;
  started_at: string;
  uptime_seconds: number;
  components: ComponentStatus[];
}

export interface CalibrationBin {
  lower: number;
  upper: number;
  mean_predicted: number;
  observed_frequency: number;
  count: number;
}

export interface ModelMetrics {
  model: "baseline" | "poisson" | "elo" | "blend";
  matches: number;
  log_loss: number;
  brier_score: number;
  accuracy: number;
  calibration: CalibrationBin[];
}

export interface BacktestReport {
  competitions: string[];
  matches_evaluated: number;
  warmup_matches: number;
  poisson_weight: number;
  outcome_frequencies: { home_win: number; draw: number; away_win: number };
  metrics: ModelMetrics[];
}

export type BroadcastState = "stopped" | "running" | "paused";

/** simulated = fake viewers; relay = real TikTok comments typed in by a moderator; tiktok = needs authorized API */
export type Audience = "simulated" | "relay" | "tiktok";

export interface RelayRequest {
  viewer_name: string;
  kind?: "comment" | "join" | "like" | "gift" | "follow" | "share";
  text?: string;
  gift_name?: string;
  count?: number;
}

export interface RelayResult {
  event_id?: string;
  accepted: boolean;
  reason: string | null;
  priority?: number | null;
}

export interface BroadcastStatus {
  state: BroadcastState;
  source: string;
  audience: Audience;
  source_is_simulated: boolean;
  source_error: string | null;
  started_at: string | null;
  uptime_seconds: number;
  queue_size: number;
  replies: number;
  segments: number;
  events_received: number;
  comments_rejected: Record<string, number>;
  errors: number;
  last_error: string | null;
  speaking_until: string | null;
  connected_clients: number;
}

export type Segment = "match_preview" | "trivia" | "forex" | "poll" | "responsible_gambling";

export interface MilestoneStatus {
  id: string;
  label: string;
  metric: "likes" | "viewers" | "comments";
  target: number;
  current: number;
  reached: boolean;
}

export interface GamificationStatus {
  totals: Record<"viewers" | "comments" | "likes" | "gifts" | "follows" | "shares", number>;
  milestones: MilestoneStatus[];
  outfit: string;
  background: string;
  trivia: {
    question_en: string;
    question_sw: string;
    options: string[];
    closes_at: string;
    answers: number;
    winners: string[];
  } | null;
  poll: {
    match_id: string;
    home_team: string;
    away_team: string;
    closes_at: string;
    votes: { home: number; draw: number; away: number };
  } | null;
  leaderboard: { viewer_name: string; points: number }[];
  last_poll_result: {
    home_team: string;
    away_team: string;
    votes: { home: number; draw: number; away: number };
    total: number;
  } | null;
  rules: string;
}

export interface LiveEventData {
  event_id: string;
  platform: string;
  viewer_id: string;
  viewer_name: string;
  kind: "comment" | "join" | "like" | "gift" | "follow" | "share";
  text: string | null;
  count: number;
  gift_name: string | null;
  received_at: string;
  is_simulated: boolean;
  accepted?: boolean;
  reason?: string | null;
  priority?: number | null;
}

export interface SayData {
  source: string;
  viewer_name?: string | null;
  comment?: string | null;
  text: string;
  speech: SpeechCue | null;
}

export interface GameUpdate {
  kind: string;
  viewer_name: string | null;
  message: string;
  data: Record<string, unknown>;
}

export type LiveMessage =
  | { type: "snapshot"; at?: string; data: { state: BroadcastStatus; gamification: GamificationStatus; recent: LiveMessage[] } }
  | { type: "event"; at: string; data: LiveEventData }
  | { type: "say"; at: string; data: SayData }
  | { type: "game"; at: string; data: GameUpdate }
  | { type: "state"; at: string; data: BroadcastStatus }
  | { type: "alert"; at: string; data: { message: string } };
