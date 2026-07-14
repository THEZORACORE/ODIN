import { LatestDateResponse, PicksResponse } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export interface PicksRequest {
  sport: string;
  game_date: string;
  min_ev: number;
  min_confidence: number;
  max_picks: number;
  bankroll: number;
}

export async function fetchLatestDate(): Promise<LatestDateResponse> {
  const res = await fetch(`${API_BASE}/picks/latest-date/`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchPicks(req: PicksRequest): Promise<PicksResponse> {
  const res = await fetch(`${API_BASE}/picks/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}
