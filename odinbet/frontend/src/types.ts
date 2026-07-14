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
