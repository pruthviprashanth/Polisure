"use client";

import { ScenarioChart, ScoreChart } from "@/components/charts";
import { useEffect, useState } from "react";
import { NumberField, ProfileForm } from "@/components/ProfileForm";
import { ClauseChip, Disclaimer, ErrorBox, Loading, MetaBadge, VerdictBadge, VerifiedBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { inr, prettyCategory } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { PolicyListItem, RecommendResponse } from "@/lib/types";

// Category names used by the backend's closed enum.
const CLAIMS = ["appendectomy", "cataract", "hernia", "joint_replacement", "maternity"];

const PROGRESS = [
  "Simulating each likely claim on every policy…",
  "Applying waiting periods for a new policy…",
  "Scoring the policies in code…",
  "Writing the reasons…",
  "Still working — thanks for your patience…",
];

export default function RecommendPage() {
  const { profile, setProfile, wallet } = useStore();
  const [library, setLibrary] = useState<PolicyListItem[]>([]);
  const [libError, setLibError] = useState<unknown>(null);
  const [claims, setClaims] = useState<string[]>(["appendectomy", "cataract"]);
  const [bills, setBills] = useState<Record<string, number | null>>({});
  const [premiums, setPremiums] = useState<Record<string, number | null>>({});
  const [onlyWallet, setOnlyWallet] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<RecommendResponse | null>(null);

  useEffect(() => {
    api.listPolicies().then(setLibrary, setLibError);
  }, []);

  const candidates = onlyWallet ? library.filter((p) => wallet.includes(p.policy_id)) : library;
  const toggleClaim = (c: string) => setClaims(claims.includes(c) ? claims.filter((x) => x !== c) : [...claims, c]);

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    const assumed = Object.fromEntries(claims.filter((c) => bills[c]).map((c) => [c, bills[c] as number]));
    const prem = Object.fromEntries(candidates.filter((p) => premiums[p.policy_id]).map((p) => [p.policy_id, premiums[p.policy_id] as number]));
    try {
      setResult(
        await api.recommend({
          // A newly bought policy is 0 months old, so waiting periods apply.
          profile: { ...profile, policy_age_months: 0 },
          likely_claims: claims,
          ...(Object.keys(assumed).length ? { assumed_bills: assumed } : {}),
          ...(Object.keys(prem).length ? { annual_premiums: prem } : {}),
          ...(onlyWallet ? { policy_ids: candidates.map((p) => p.policy_id) } : {}),
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">Find a policy to buy</h1>
        <p className="mt-1 text-slate-600">
          Tell us which claims you think are likely. We simulate each one on every policy in the library — as a brand-new
          policy, so waiting periods apply — and rank them by what they would actually pay.
        </p>
      </div>

      <Disclaimer text="This compares coverage terms for the claims you list. It is not financial advice, and premiums are only considered if you enter them." />

      <section className="card space-y-4">
        <h2 className="h2">1. About you</h2>
        <ProfileForm profile={profile} onChange={setProfile} hidePolicyAge />
      </section>

      <section className="card space-y-4">
        <h2 className="h2">2. Likely claims</h2>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Likely claims">
          {CLAIMS.map((c) => {
            const on = claims.includes(c);
            return (
              <button
                key={c}
                type="button"
                aria-pressed={on}
                onClick={() => toggleClaim(c)}
                className={`rounded-full border px-3 py-1.5 text-sm ${
                  on ? "border-teal-700 bg-teal-700 text-white" : "border-slate-300 bg-white hover:bg-slate-50"
                }`}
              >
                {on ? "✓ " : ""}
                {prettyCategory(c)}
              </button>
            );
          })}
        </div>
        {claims.length > 0 && (
          <div>
            <div className="label">Expected bill size (optional — otherwise an illustrative default is used)</div>
            <div className="grid gap-3 sm:grid-cols-3">
              {claims.map((c) => (
                <NumberField
                  key={c}
                  id={`bill-${c}`}
                  label={prettyCategory(c)}
                  prefix="₹"
                  placeholder="default"
                  value={bills[c] ?? null}
                  onChange={(n) => setBills({ ...bills, [c]: n })}
                />
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="card space-y-4">
        <h2 className="h2">3. Policies to compare</h2>
        {!!libError && <ErrorBox error={libError} />}
        {wallet.length > 0 && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyWallet} onChange={(e) => setOnlyWallet(e.target.checked)} className="h-4 w-4 accent-teal-700" />
            Only the policies in my wallet
          </label>
        )}
        <p className="text-sm text-slate-600">
          Policy documents don&apos;t contain premiums. Enter a quoted annual premium if you have one (optional).
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {candidates.map((p) => (
            <NumberField
              key={p.policy_id}
              id={`prem-${p.policy_id}`}
              label={`${p.name}${p.computable === false ? " (can't compute payouts)" : ""}`}
              prefix="₹"
              placeholder="annual premium"
              value={premiums[p.policy_id] ?? null}
              onChange={(n) => setPremiums({ ...premiums, [p.policy_id]: n })}
            />
          ))}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn btn-primary" onClick={run} disabled={busy || claims.length === 0 || candidates.length === 0}>
          Rank policies
        </button>
        {claims.length === 0 && <span className="text-sm text-slate-500">Pick at least one likely claim.</span>}
      </div>
      {busy && <Loading steps={PROGRESS} />}
      {!!error && <ErrorBox error={error} onRetry={run} />}

      {result && (
        <section className="space-y-4" aria-labelledby="ranked">
          <div className="flex flex-wrap items-center gap-3">
            <h2 id="ranked" className="h2">
              Ranking
            </h2>
            <MetaBadge meta={result.meta} />
          </div>
          {result.why && <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-950">{result.why}</p>}
          <div className="grid gap-3 lg:grid-cols-2">
            <ScoreChart ranked={result.ranked} />
            <ScenarioChart ranked={result.ranked} />
          </div>
          <ol className="space-y-3">
            {result.ranked.map((r, i) => {
              const best = r.policy_id === result.best_policy_id;
              return (
                <li key={r.policy_id} className={`card space-y-3 ${best ? "ring-2 ring-emerald-600" : ""} ${r.computable ? "" : "bg-slate-50 text-slate-600"}`}>
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-lg font-bold text-slate-400">#{i + 1}</span>
                    <h3 className="min-w-0 flex-1 font-semibold">{r.name}</h3>
                    {best && <span className="rounded bg-emerald-700 px-2 py-0.5 text-xs font-semibold text-white">Best match</span>}
                    {r.computable ? (
                      <span className="text-right">
                        <span className="block text-2xl font-semibold text-teal-800 tabular-nums">{r.score ?? "—"}</span>
                        <span className="block text-xs text-slate-500">score / 100</span>
                      </span>
                    ) : (
                      <span className="rounded bg-amber-400 px-2 py-0.5 text-xs font-semibold text-amber-950">Can&apos;t compute payouts</span>
                    )}
                  </div>

                  {r.scenario_results.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[480px] text-sm">
                        <thead>
                          <tr className="border-b border-slate-200 text-left text-slate-500">
                            <th className="py-1.5 pr-3 font-medium">Claim</th>
                            <th className="py-1.5 pr-3 text-right font-medium">Bill</th>
                            <th className="py-1.5 pr-3 text-right font-medium">Pays</th>
                            <th className="py-1.5 font-medium">Verdict</th>
                          </tr>
                        </thead>
                        <tbody>
                          {r.scenario_results.map((s) => (
                            <tr key={s.category} className="border-b border-slate-100 align-top">
                              <td className="py-1.5 pr-3">
                                {prettyCategory(s.category)}
                                {s.note && <div className="text-xs text-slate-500">{s.note}</div>}
                              </td>
                              <td className="py-1.5 pr-3 text-right tabular-nums">{inr(s.billed)}</td>
                              <td className="py-1.5 pr-3 text-right font-semibold tabular-nums">{inr(s.payout)}</td>
                              <td className="py-1.5">
                                <VerdictBadge verdict={s.verdict} size="sm" />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {r.reasons.length > 0 && (
                    <ul className="space-y-1.5 text-sm">
                      {r.reasons.map((x, j) => (
                        <li key={j} className="flex flex-wrap items-center gap-2">
                          <span>• {x.text}</span>
                          <ClauseChip policyId={r.policy_id} clause={x.clause} page={x.page} quote={x.quote} />
                          {x.quote && typeof x.verified === "boolean" && <VerifiedBadge verified={x.verified} />}
                        </li>
                      ))}
                    </ul>
                  )}
                  {r.premium_note && <p className="text-sm text-slate-700">{r.premium_note}</p>}
                </li>
              );
            })}
          </ol>

          {result.assumptions.length > 0 && (
            <section className="card space-y-2">
              <h3 className="font-semibold">Assumptions</h3>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {result.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </section>
          )}
          <Disclaimer text={result.disclaimer} />
        </section>
      )}
    </div>
  );
}
