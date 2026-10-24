"use client";

import { ClauseChip, Disclaimer, Quote, VerdictBadge, VerifiedBadge } from "@/components/ui";
import { inr } from "@/lib/format";
import type { Verdict } from "@/lib/types";

export function VerdictView({ v, policyId, policyName }: { v: Verdict; policyId?: string | null; policyName?: string }) {
  const review = v.verdict === "NEEDS_REVIEW";
  return (
    <div className="space-y-5">
      <section className="card flex flex-wrap items-center gap-x-8 gap-y-4">
        <div className="space-y-2">
          {policyName && <div className="text-sm text-slate-500">{policyName}</div>}
          <VerdictBadge verdict={v.verdict} />
        </div>
        <dl className="flex flex-wrap gap-x-8 gap-y-2">
          <div>
            <dt className="text-sm text-slate-500">Billed</dt>
            <dd className="text-2xl font-semibold">{inr(v.billed)}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-500">Estimated payout</dt>
            <dd className="text-2xl font-semibold text-teal-800">{v.payout === null ? "Not estimated" : inr(v.payout)}</dd>
          </div>
          {v.payout !== null && v.billed !== null && v.billed > v.payout && (
            <div>
              <dt className="text-sm text-slate-500">You pay</dt>
              <dd className="text-2xl font-semibold text-red-800">{inr(v.billed - v.payout)}</dd>
            </div>
          )}
        </dl>
      </section>

      {review && v.abstain_reason && (
        <section className="rounded-xl border border-indigo-300 bg-indigo-50 p-4" role="note">
          <h2 className="font-semibold text-indigo-900">Why we won&apos;t guess</h2>
          <p className="mt-1 text-sm text-indigo-900">{v.abstain_reason}</p>
        </section>
      )}

      <section className="card space-y-2">
        <h2 className="h2">Why</h2>
        <p>{v.why}</p>
      </section>

      {v.trace.length > 0 && (
        <section className="card space-y-2">
          <h2 className="h2">How we calculated it</h2>
          <p className="text-xs text-slate-500">Every number below is computed in code from the policy rules; the language model never sets a payout.</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="py-2 pr-3 font-medium">Step</th>
                  <th className="py-2 pr-3 text-right font-medium">Before</th>
                  <th className="py-2 pr-3 text-right font-medium">After</th>
                  <th className="py-2 font-medium">Clause</th>
                </tr>
              </thead>
              <tbody>
                {v.trace.map((t, i) => {
                  const total = t.step === "total";
                  const changed = t.before !== null && t.after !== null && t.after !== t.before;
                  return (
                    <tr key={i} className={`border-b border-slate-100 ${total ? "bg-slate-50 font-semibold" : ""}`}>
                      <td className="py-2 pr-3">{t.label}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{inr(t.before)}</td>
                      <td className={`py-2 pr-3 text-right tabular-nums ${changed && !total ? "text-red-800" : ""}`}>
                        {t.after === null ? "not computed" : inr(t.after)}
                      </td>
                      <td className="py-2">
                        <ClauseChip policyId={policyId} clause={t.clause} page={t.page} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {v.counterfactuals.length > 0 && (
        <section className="space-y-2">
          <h2 className="h2">What if…</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {v.counterfactuals.map((c, i) => (
              <article key={i} className="card border-l-4 border-l-teal-600">
                <div className="text-sm text-slate-700">{c.change}</div>
                <div className="mt-1 text-xl font-semibold">{c.new_payout === null ? "—" : inr(c.new_payout)}</div>
                {c.delta !== null && c.delta !== 0 && (
                  <div className={`text-sm font-medium ${c.delta > 0 ? "text-emerald-800" : "text-red-800"}`}>
                    {c.delta > 0 ? "+" : ""}
                    {inr(c.delta)} vs this estimate
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      {v.citations.length > 0 && (
        <section className="card space-y-3">
          <h2 className="h2">Clauses cited</h2>
          <ul className="space-y-3">
            {v.citations.map((c, i) => (
              <li key={i} className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <ClauseChip policyId={policyId} clause={c.clause} page={c.page} quote={c.quote} />
                  <VerifiedBadge verified={c.verified} />
                </div>
                <Quote>{c.quote}</Quote>
              </li>
            ))}
          </ul>
        </section>
      )}

      {v.next_steps.length > 0 && (
        <section className="card space-y-2">
          <h2 className="h2">Next steps</h2>
          <ol className="list-decimal space-y-1 pl-5">
            {v.next_steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </section>
      )}

      <Disclaimer text={v.disclaimer} />
    </div>
  );
}
