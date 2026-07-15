"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchBacktest,
  fetchLatestDate,
  fetchMetrics,
  fetchPicks,
  PicksRequest,
} from "@/lib/api";
import { BacktestResponse, MetricsResponse, PicksResponse } from "@/types";
import PickCard from "./PickCard";

export default function Dashboard() {
  const [req, setReq] = useState<PicksRequest>({
    sport: "nba",
    game_date: "",
    min_ev: 0.0,
    min_confidence: 0.5,
    max_picks: 20,
    bankroll: 1000,
  });

  const [data, setData] = useState<PicksResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [backtest, setBacktest] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dateLoading, setDateLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLatestDate()
      .then((res) => {
        const latest = res.latest_date;
        if (latest) {
          setReq((prev) => ({ ...prev, game_date: latest }));
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setDateLoading(false));

    fetchMetrics()
      .then(setMetrics)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));

    fetchBacktest()
      .then(setBacktest)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const totalUnits = useMemo(
    () => (data?.picks ?? []).reduce((sum, p) => sum + p.recommended_units, 0),
    [data]
  );
  const avgEv = useMemo(
    () =>
      data && data.picks.length > 0
        ? data.picks.reduce((sum, p) => sum + p.ev, 0) / data.picks.length
        : 0,
    [data]
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetchPicks(req);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900">ODINBET</h1>
        <p className="text-slate-600">AI-powered, explainable sports betting research.</p>
      </header>

      <div className="mb-6 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">
        For entertainment and research only. Picks are not financial advice. Set limits,
        never bet more than you can afford to lose.
      </div>

      {(metrics || backtest) && (
        <details className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <summary className="cursor-pointer text-sm font-semibold text-slate-900">
            Model performance
          </summary>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {metrics && (
              <>
                <div>
                  <p className="text-xs text-slate-500">ROC-AUC</p>
                  <p className="text-lg font-semibold text-slate-900">
                    {(metrics.metrics.roc_auc * 100).toFixed(1)}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Accuracy</p>
                  <p className="text-lg font-semibold text-slate-900">
                    {(metrics.metrics.accuracy * 100).toFixed(1)}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Brier score</p>
                  <p className="text-lg font-semibold text-slate-900">
                    {metrics.metrics.brier_score.toFixed(3)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Log loss</p>
                  <p className="text-lg font-semibold text-slate-900">
                    {metrics.metrics.log_loss.toFixed(3)}
                  </p>
                </div>
              </>
            )}
            {backtest && (
              <>
                <div>
                  <p className="text-xs text-slate-500">Backtest yield (ROI)</p>
                  <p className="text-lg font-semibold text-slate-900">
                    {(backtest.roi * 100).toFixed(2)}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Backtest profit</p>
                  <p className="text-lg font-semibold text-slate-900">
                    {backtest.profit.toFixed(0)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Win / loss</p>
                  <p className="text-lg font-semibold text-slate-900">
                    {backtest.wins} / {backtest.losses}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Test games</p>
                  <p className="text-lg font-semibold text-slate-900">{backtest.n_games}</p>
                </div>
              </>
            )}
          </div>
        </details>
      )}

      <form
        onSubmit={handleSubmit}
        className="mb-8 grid grid-cols-1 gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:grid-cols-2 lg:grid-cols-6"
      >
        <div>
          <label className="block text-xs font-medium text-slate-700">Sport</label>
          <select
            className="mt-1 w-full rounded border border-slate-300 px-2 py-2 text-sm"
            value={req.sport}
            onChange={(e) => setReq({ ...req, sport: e.target.value })}
          >
            <option value="nba">NBA</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700">Date</label>
          <input
            type="date"
            className="mt-1 w-full rounded border border-slate-300 px-2 py-2 text-sm"
            value={req.game_date}
            onChange={(e) => setReq({ ...req, game_date: e.target.value })}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700">Min EV</label>
          <input
            type="number"
            step="0.01"
            min="-1"
            max="1"
            className="mt-1 w-full rounded border border-slate-300 px-2 py-2 text-sm"
            value={req.min_ev}
            onChange={(e) => setReq({ ...req, min_ev: parseFloat(e.target.value) })}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700">Min confidence</label>
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            className="mt-1 w-full rounded border border-slate-300 px-2 py-2 text-sm"
            value={req.min_confidence}
            onChange={(e) =>
              setReq({ ...req, min_confidence: parseFloat(e.target.value) })
            }
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700">Bankroll</label>
          <input
            type="number"
            min="1"
            className="mt-1 w-full rounded border border-slate-300 px-2 py-2 text-sm"
            value={req.bankroll}
            onChange={(e) => setReq({ ...req, bankroll: parseFloat(e.target.value) })}
          />
        </div>

        <div className="flex items-end">
          <button
            type="submit"
            disabled={loading || dateLoading || !req.game_date}
            className="w-full rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? "Loading..." : "Get Picks"}
          </button>
        </div>
      </form>

      {error && (
        <div className="mb-6 rounded-lg bg-rose-50 p-4 text-sm text-rose-900">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs text-slate-500">Picks</p>
              <p className="text-2xl font-semibold text-slate-900">{data.picks.length}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs text-slate-500">Avg EV</p>
              <p
                className={`text-2xl font-semibold ${
                  avgEv >= 0 ? "text-emerald-700" : "text-rose-700"
                }`}
              >
                {avgEv >= 0 ? "+" : ""}
                {(avgEv * 100).toFixed(2)}%
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs text-slate-500">Total units</p>
              <p className="text-2xl font-semibold text-slate-900">
                {totalUnits.toFixed(2)}
              </p>
              <p className="text-xs text-slate-500">
                Max daily: {(req.bankroll * 0.05).toFixed(0)}
              </p>
            </div>
          </div>

          {data.warning && (
            <div className="mb-6 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">
              {data.warning}
            </div>
          )}

          <div className="space-y-4">
            {data.picks.map((pick) => (
              <PickCard key={pick.game_id} pick={pick} />
            ))}
          </div>

          <div className="mt-8 text-xs text-slate-500">
            Odds source: {data.odds_source}. Generated for {data.generated_at}.
          </div>
        </>
      )}
    </main>
  );
}
