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
