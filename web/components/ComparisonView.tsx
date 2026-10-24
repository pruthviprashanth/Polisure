"use client";

import { useState } from "react";
import { ComparisonChart } from "@/components/charts";
import { VerdictView } from "@/components/VerdictView";
import { VerdictBadge } from "@/components/ui";
import { inr } from "@/lib/format";
import type { Comparison } from "@/lib/types";

export function ComparisonView({ c }: { c: Comparison }) {
  const [tab, setTab] = useState<string>(c.recommended_policy_id || c.results[0]?.policy_id);
  const name = (id: string) => c.results.find((r) => r.policy_id === id)?.name || id;
  const active = c.results.find((r) => r.policy_id === tab) || c.results[0];

  return (
    <div className="space-y-5">
      <section className="card space-y-3">
        <h2 className="h2">Your policies compared</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2 pr-3 font-medium">Policy</th>
                <th className="py-2 pr-3 font-medium">Verdict</th>
                <th className="py-2 pr-3 text-right font-medium">Estimated payout</th>
                <th className="py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {c.results.map((r) => {
                const rec = r.policy_id === c.recommended_policy_id;
                const best = r.estimate_quality === "best_case" && r.verdict.verdict !== "NEEDS_REVIEW";
                const usable = r.computable || best;
                return (
                  <tr
                    key={r.policy_id}
                    className={`border-b border-slate-100 ${rec ? "bg-emerald-50" : ""} ${usable ? "" : "text-slate-500"}`}
                  >
                    <td className="py-2 pr-3">
                      <div className="font-medium">{r.name}</div>
                      {rec && <span className="rounded bg-emerald-700 px-1.5 py-0.5 text-xs font-semibold text-white">Recommended</span>}
                      {best && (
                        <span className="ml-1 rounded bg-indigo-700 px-1.5 py-0.5 text-xs font-semibold text-white" title={(r.verdict.assumptions ?? []).join("; ")}>
                          Best case
                        </span>
                      )}
                      {!usable && (
                        <div className="line-clamp-2 text-xs" title={r.verdict.abstain_reason || undefined}>
                          Can&apos;t compute payouts: {r.verdict.abstain_reason || "structure not supported"}
                        </div>
                      )}
                    </td>
                    <td className={`py-2 pr-3 ${usable ? "" : "opacity-60"}`}>
                      <VerdictBadge verdict={r.verdict.verdict} size="sm" />
                    </td>
                    <td className="py-2 pr-3 text-right font-semibold tabular-nums">
                      {r.verdict.payout === null ? "—" : `${best ? "up to " : ""}${inr(r.verdict.payout)}`}
                    </td>
                    <td className="py-2 text-right">
                      <button type="button" className="text-sm text-teal-800 underline" onClick={() => setTab(r.policy_id)}>
                        Details
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className={`rounded-lg p-3 text-sm ${c.recommended_policy_id ? "bg-emerald-50 text-emerald-950" : "bg-indigo-50 text-indigo-950"}`}>
          {c.recommended_policy_id && <strong>Claim with {name(c.recommended_policy_id)}: </strong>}
          {c.recommendation_reason}
        </p>
      </section>

      <ComparisonChart results={c.results} />

      {c.combined && (
        <section className="card space-y-2 border-l-4 border-l-teal-600">
          <h2 className="h2">Claiming from more than one policy</h2>
          {c.combined.possible ? (
            <>
              <div className="text-sm text-slate-600">Estimated combined payout</div>
              <div className="text-2xl font-semibold text-teal-800">{inr(c.combined.total_payout)}</div>
              <ul className="text-sm">
                {c.combined.split.map((s, i) => (
                  <li key={s.policy_id} className="flex justify-between border-b border-slate-100 py-1">
                    <span>
                      {i + 1}. {name(s.policy_id)}
                    </span>
                    <span className="tabular-nums">{inr(s.payout)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm">A combined claim could not be estimated.</p>
          )}
          <p className="text-xs text-slate-600">{c.combined.note}</p>
        </section>
      )}

      <section className="space-y-3">
        <div role="tablist" aria-label="Full verdict per policy" className="flex flex-wrap gap-1 border-b border-slate-200">
          {c.results.map((r) => (
            <button
              key={r.policy_id}
              type="button"
              role="tab"
              aria-selected={r.policy_id === active?.policy_id}
              onClick={() => setTab(r.policy_id)}
              className={`-mb-px rounded-t-lg border px-3 py-2 text-sm ${
                r.policy_id === active?.policy_id
                  ? "border-slate-200 border-b-white bg-white font-semibold"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              {r.name}
            </button>
          ))}
        </div>
        {active && (
          <div role="tabpanel">
            <VerdictView key={active.policy_id} v={active.verdict} policyId={active.policy_id} policyName={active.name} />
          </div>
        )}
      </section>
    </div>
  );
}
