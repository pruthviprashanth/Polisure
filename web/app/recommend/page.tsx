"use client";

import { ScenarioChart, ScoreChart } from "@/components/charts";
import { Fragment, useEffect, useState } from "react";
import { NumberField, ProfileForm } from "@/components/ProfileForm";
import { ClauseChip, Disclaimer, ErrorBox, Loading, MetaBadge, VerdictBadge, VerifiedBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { inr, prettyCategory, qualityLabel } from "@/lib/format";
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
  const { profile, setProfile, wallet, addPolicy, policy, setPolicy } = useStore();
  const [library, setLibrary] = useState<PolicyListItem[]>([]);
  const [libError, setLibError] = useState<unknown>(null);
  const [claims, setClaims] = useState<string[]>(["appendectomy", "cataract"]);
  const [bills, setBills] = useState<Record<string, number | null>>({});
  const [premiums, setPremiums] = useState<Record<string, number | null>>({});
  const [onlyWallet, setOnlyWallet] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [claimAfter, setClaimAfter] = useState(1);
  const [adding, setAdding] = useState<string | null>(null);

  useEffect(() => {
    api.listPolicies().then(setLibrary, setLibError);
  }, []);

  // The catalog = bundled policies (data/library); a user's own uploads are not candidates unless "only my policies" is ticked.
  const catalog = library.filter((p) => p.catalog !== false);
  const candidates = onlyWallet ? library.filter((p) => wallet.includes(p.policy_id)) : catalog;
  const toggleClaim = (c: string) => setClaims(claims.includes(c) ? claims.filter((x) => x !== c) : [...claims, c]);

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    setShowAll(false);
    const assumed = Object.fromEntries(claims.filter((c) => bills[c]).map((c) => [c, bills[c] as number]));
    const prem = Object.fromEntries(candidates.filter((p) => premiums[p.policy_id]).map((p) => [p.policy_id, premiums[p.policy_id] as number]));
    try {
      setResult(
        await api.recommend({
          // A newly bought policy is 0 months old, so waiting periods apply.
          profile: { ...profile, policy_age_months: 0 },
          likely_claims: claims,
          claim_after_months: claimAfter,
          ...(Object.keys(assumed).length ? { assumed_bills: assumed } : {}),
          ...(Object.keys(prem).length ? { annual_premiums: prem } : {}),
          policy_ids: candidates.map((p) => p.policy_id),
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function addToMine(id: string) {
    setAdding(id);
    try {
      addPolicy(id);
      if (!policy) setPolicy(await api.getPolicy(id));
    } catch (e) {
      setError(e);
    } finally {
      setAdding(null);
    }
  }

  const shown = result ? (showAll ? result.ranked : result.ranked.slice(0, 5)) : [];
  const chartRanked = result ? result.ranked.filter((r) => (r.computable || r.estimate_quality === "best_case") && r.eligible !== false).slice(0, 5) : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">Find a policy to buy</h1>
        <p className="mt-1 text-slate-600">
          Tell us which claims you think are likely. We simulate each one on every policy in our catalog — as a brand-new
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
        <div className="max-w-md">
          <label htmlFor="claim-after" className="label">
            When do you expect to claim?
          </label>
          <select id="claim-after" className="input" value={claimAfter} onChange={(e) => setClaimAfter(Number(e.target.value))}>
            <option value={1}>Soon after buying (after the first month)</option>
            <option value={24}>In about 2 years</option>
            <option value={48}>In about 4 years</option>
          </select>
          <p className="mt-1 text-xs text-slate-500">Waiting periods longer than this still block a claim.</p>
        </div>
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

      <section className="card space-y-3">
        <h2 className="h2">3. Policies to compare</h2>
        {!!libError && <ErrorBox error={libError} />}
        <p className="text-sm text-slate-700">
          {library.length === 0 && !libError ? (
            "Loading the catalog…"
          ) : (
            <>
              Comparing <strong>{candidates.length}</strong> {onlyWallet ? "of my policies" : "catalog policies"}
              {` (${candidates.filter((p) => p.computable !== false).length} exact, ${candidates.filter((p) => p.estimate_quality === "best_case").length} best-case, ${candidates.filter((p) => p.estimate_quality === "terms_only").length} terms-only)`}.
            </>
          )}
        </p>
        {wallet.length > 0 && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyWallet} onChange={(e) => setOnlyWallet(e.target.checked)} className="h-4 w-4 accent-teal-700" />
            Only compare the policies I already own
          </label>
        )}
        <details className="rounded-lg border border-slate-200 p-3">
          <summary className="cursor-pointer text-sm font-medium">Add quoted premiums (optional)</summary>
          <p className="mt-2 text-sm text-slate-600">
            Policy documents don&apos;t contain premiums. Enter a quoted annual premium for any policy you have a price for.
          </p>
          <div className="mt-3 grid max-h-80 gap-3 overflow-y-auto sm:grid-cols-2">
            {candidates.map((p) => (
              <NumberField
                key={p.policy_id}
                id={`prem-${p.policy_id}`}
                label={`${p.name}${qualityLabel(p.estimate_quality, p.computable) ? ` (${qualityLabel(p.estimate_quality, p.computable)})` : ""}`}
                prefix="₹"
                placeholder="annual premium"
                value={premiums[p.policy_id] ?? null}
                onChange={(n) => setPremiums({ ...premiums, [p.policy_id]: n })}
              />
            ))}
          </div>
        </details>
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
            <ScoreChart ranked={chartRanked} />
            <ScenarioChart ranked={chartRanked} />
          </div>
          <p className="text-sm text-slate-600">
            Showing {shown.length} of {result.ranked.length} policies; the charts show the top {chartRanked.length}.
          </p>
          <ol className="space-y-3">
            {shown.map((r, i) => {
              const best = r.policy_id === result.best_policy_id;
              const groupOf = (x: typeof r) => (x.eligible === false ? "ineligible" : x.computable ? "scored" : x.estimate_quality === "best_case" ? "bestcase" : "terms");
              const group = groupOf(r);
              const prevGroup = i === 0 ? "" : groupOf(shown[i - 1]);
              const heading =
                group === prevGroup
                  ? null
                  : group === "scored"
                    ? { t: "Ranked on simulated payouts", d: "Payouts for your likely claims were computed exactly from these policies' rules." }
                    : group === "bestcase"
                      ? { t: "Best-case estimates", d: "These wordings leave some limits out (often the room-rent limit, which is in the policy schedule). Payouts are upper bounds under the stated assumptions, so they are not directly comparable with the exact ones above." }
                    : group === "terms"
                      ? { t: "Compared on terms only", d: "Their room-rent or other limits cannot be computed from the wording (often set in the schedule), so payouts are not simulated. Ranked on waiting periods, exclusions and co-pay." }
                      : { t: "Not available at your age", d: "These policies do not accept your age." };
              return (
                <Fragment key={r.policy_id}>
                {heading && (
                  <li className="pt-2">
                    <h3 className="font-semibold">{heading.t}</h3>
                    <p className="text-sm text-slate-600">{heading.d}</p>
                  </li>
                )}
                <li className={`card space-y-3 ${best ? "ring-2 ring-emerald-600" : ""} ${r.computable ? "" : "bg-slate-50 text-slate-600"}`}>
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-lg font-bold text-slate-400">#{i + 1}</span>
                    <h3 className="min-w-0 flex-1 font-semibold">{r.name}</h3>
                    {best && <span className="rounded bg-emerald-700 px-2 py-0.5 text-xs font-semibold text-white">Best match</span>}
                    {!best && r.policy_id === result.best_terms_policy_id && (
                      <span className="rounded bg-indigo-700 px-2 py-0.5 text-xs font-semibold text-white">Best on terms</span>
                    )}
                    {r.estimate_quality === "best_case" && r.eligible !== false && (
                      <span className="rounded bg-indigo-700 px-2 py-0.5 text-xs font-semibold text-white">Best case</span>
                    )}
                    {r.eligible === false ? (
                      <span className="rounded bg-slate-300 px-2 py-0.5 text-xs font-semibold text-slate-800">Not eligible</span>
                    ) : r.computable || r.estimate_quality === "best_case" ? (
                      <span className="text-right">
                        <span className="block text-2xl font-semibold text-teal-800 tabular-nums">{r.score ?? "—"}</span>
                        <span className="block text-xs text-slate-500">{r.computable ? "score / 100" : "best-case score / 100"}</span>
                      </span>
                    ) : (
                      <span className="text-right">
                        <span className="block text-2xl font-semibold text-indigo-800 tabular-nums">{r.terms_score ?? "—"}</span>
                        <span className="block text-xs text-slate-500">terms score / 100</span>
                      </span>
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
                              <td className="py-1.5 pr-3 text-right font-semibold tabular-nums">{s.payout === null ? "not computed" : inr(s.payout)}</td>
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
                  {r.eligible !== false && (
                    <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                      {wallet.includes(r.policy_id) ? (
                        <span className="rounded bg-emerald-100 px-2 py-1 text-sm font-medium text-emerald-900">✓ In my policies</span>
                      ) : (
                        <button type="button" className="btn btn-primary py-1" disabled={adding !== null} onClick={() => addToMine(r.policy_id)}>
                          {adding === r.policy_id ? "Adding…" : "+ Add to my policies"}
                        </button>
                      )}
                      <span className="text-xs text-slate-500">Adds it to your list; premiums and purchase happen with the insurer.</span>
                    </div>
                  )}
                </li>
                </Fragment>
              );
            })}
          </ol>
          {result.ranked.length > 5 && (
            <button type="button" className="btn btn-secondary" onClick={() => setShowAll((s) => !s)}>
              {showAll ? "Show only the top 5" : `Show all ${result.ranked.length} policies`}
            </button>
          )}

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
