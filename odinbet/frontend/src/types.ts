export interface KeyFactor {
  feature: string;
  value: number;
  direction: "up" | "down";
}

export interface Pick {
  game_id: string;
  matchup: string;
  market: string;
  selection: string;
  model_probability: number;
  decimal_odds: number;
  ev: number;
  recommended_units: number;
  confidence: number;
  rationale: string;
  key_factors: KeyFactor[];
}

export interface PicksResponse {
  generated_at: string;
  sport: string;
  odds_source: string;
  bankroll: number;
  picks: Pick[];
  warning: string | null;
}

export interface LatestDateResponse {
  latest_date: string | null;
  total_games: number;
}

export interface MetricsResponse {
  metrics: Record<string, number>;
  top_features: { feature: string; importance: number }[];
}

export interface BacktestResponse {
  n_games: number;
  roi: number;
  profit: number;
  wagered: number;
  final_bankroll: number;
  bankroll_return: number;
  wins: number;
  losses: number;
  pushes: number;
}
