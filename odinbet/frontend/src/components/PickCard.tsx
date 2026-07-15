"use client";

import { Pick } from "@/types";

export default function PickCard({ pick }: { pick: Pick }) {
  const evPositive = pick.ev >= 0;

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">{pick.matchup}</p>
          <h3 className="text-lg font-semibold text-slate-900">
            {pick.selection} — {pick.market}
          </h3>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            evPositive
              ? "bg-emerald-100 text-emerald-800"
              : "bg-rose-100 text-rose-800"
          }`}
        >
          EV {evPositive ? "+" : ""}{(pick.ev * 100).toFixed(2)}%
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <p className="text-xs text-slate-500">Model</p>
          <p className="font-medium text-slate-900">
            {(pick.model_probability * 100).toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Odds</p>
          <p className="font-medium text-slate-900">{pick.decimal_odds.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Units</p>
          <p className="font-medium text-slate-900">
            {pick.recommended_units.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Confidence</p>
          <p className="font-medium text-slate-900">
            {(pick.confidence * 100).toFixed(1)}%
          </p>
        </div>
      </div>

      <p className="mt-4 text-sm text-slate-700">{pick.rationale}</p>

      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium text-blue-700">
          Key factors
        </summary>
        <ul className="mt-2 space-y-1 text-sm text-slate-600">
          {pick.key_factors.map((factor, idx) => (
            <li key={idx} className="flex items-center gap-2">
              <span
                className={`inline-block h-2 w-2 rounded-full ${
                  factor.direction === "up" ? "bg-emerald-500" : "bg-rose-500"
                }`}
              />
              <span>
                {factor.feature}: {factor.direction === "up" ? "favors" : "opposes"} the pick
                {factor.value ? ` (${factor.value})` : ""}
              </span>
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}
