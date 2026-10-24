"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ProfileForm } from "@/components/ProfileForm";
import { usePdf } from "@/components/PdfModal";
import { GapCharts } from "@/components/charts";
import { ClauseChip, ErrorBox, Loading, MetaBadge, Quote, VerifiedBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { SEVERITY_STYLE } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { PolicyListItem, SummaryItem } from "@/lib/types";

const UPLOAD_STEPS = [
  "Uploading the PDF…",
  "Reading the text of every page…",
  "The language model is extracting the coverage rules…",
  "Free-tier calls are paced, so this can take 20–60 s…",
  "Verifying every quote against its page…",
  "Almost there…",
];

function SummaryCard({ s, policyId }: { s: SummaryItem; policyId: string }) {
  return (
    <article className="card flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{s.label}</h3>
        <VerifiedBadge verified={s.verified} />
      </div>
      <p className="text-sm">{s.summary}</p>
      <Quote>{s.quote}</Quote>
      <div className="mt-auto">
        <ClauseChip policyId={policyId} clause={s.clause} page={s.page} quote={s.quote} />
      </div>
    </article>
  );
}

export default function MyPolicyPage() {
  const { ready, policy, setPolicy, profile, setProfile, gaps, setGaps, wallet, addPolicy } = useStore();
  const pdf = usePdf();
  const [library, setLibrary] = useState<PolicyListItem[] | null>(null);
  const [libError, setLibError] = useState<unknown>(null);
  const [busy, setBusy] = useState<"upload" | "sample" | null>(null);
  const [policyError, setPolicyError] = useState<unknown>(null);
  const [gapsBusy, setGapsBusy] = useState(false);
  const [gapsError, setGapsError] = useState<unknown>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const lastAction = useRef<() => void>(() => {});

  const loadLibrary = useCallback(() => {
    setLibError(null);
    api.listPolicies().then(setLibrary, setLibError);
  }, []);
  useEffect(loadLibrary, [loadLibrary]);

  const loadGaps = useCallback(async () => {
    if (!policy) return;
    setGapsBusy(true);
    setGapsError(null);
    try {
      setGaps(await api.gaps(policy.policy_id, profile));
    } catch (e) {
      setGapsError(e);
    } finally {
      setGapsBusy(false);
    }
  }, [policy, profile, setGaps]);

  // Fetch the gap report once a policy is chosen (and again when the profile is re-checked).
  useEffect(() => {
    if (ready && policy && !gaps && !gapsBusy && !gapsError) loadGaps();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, policy?.policy_id]);

  async function upload() {
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    lastAction.current = upload;
    setBusy("upload");
    setPolicyError(null);
    try {
      const up = await api.uploadPolicy(f);
      setPolicy(up);
      addPolicy(up.policy_id);
      loadLibrary();
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setPolicyError(e);
    } finally {
      setBusy(null);
    }
  }

  async function pickSample(id: string) {
    lastAction.current = () => pickSample(id);
    setBusy("sample");
    setPolicyError(null);
    try {
      setPolicy(await api.getPolicy(id));
    } catch (e) {
      setPolicyError(e);
    } finally {
      setBusy(null);
    }
  }

  const mine = (library ?? []).filter((p) => wallet.includes(p.policy_id));

  // With policies in the wallet but none active (e.g. after removing the active one), open the first.
  useEffect(() => {
    if (ready && !policy && !busy && library && mine.length > 0) pickSample(mine[0].policy_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, policy, library, wallet.join(",")]);

  // Real policies list dozens of exclusions; keep them behind a toggle so the key rules stay visible.
  const mainItems = policy?.summary_items.filter((s) => !s.key.startsWith("exclusion")) ?? [];
  const exclusions = policy?.summary_items.filter((s) => s.key.startsWith("exclusion")) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">My policy</h1>
        <p className="mt-1 text-slate-600">
          Upload your health policy and tell us a little about yourself. We show what the policy really says, with the exact
          clause and page, and flag the gaps that could cut a claim.
        </p>
      </div>

      <section className="card space-y-4" aria-labelledby="choose">
        <h2 id="choose" className="h2">
          1. Choose a policy
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1">
            <label htmlFor="pdf" className="label">
              Upload the policy wording (PDF with a text layer)
            </label>
            <input
              id="pdf"
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-200 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-slate-300"
            />
          </div>
          <button type="button" className="btn btn-primary" onClick={upload} disabled={!!busy}>
            Upload & read
          </button>
        </div>
        <div>
          <div className="label">
            …or choose one of your policies{" "}
            <Link href="/wallet" className="font-normal text-teal-700 underline">
              (add or remove)
            </Link>
          </div>
          {libError ? (
            <ErrorBox error={libError} onRetry={loadLibrary} />
          ) : !library ? (
            <p className="text-sm text-slate-500">Loading your policies…</p>
          ) : mine.length === 0 ? (
            <p className="text-sm text-slate-500">
              You have not added any policies yet. Upload one above, or{" "}
              <Link href="/wallet" className="text-teal-700 underline">
                add a sample on the My policies page
              </Link>
              .
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {mine.map((p) => (
                <button
                  key={p.policy_id}
                  type="button"
                  disabled={!!busy}
                  onClick={() => pickSample(p.policy_id)}
                  className={`btn btn-secondary ${policy?.policy_id === p.policy_id ? "ring-2 ring-teal-600" : ""}`}
                >
                  {p.name} <span className="text-xs text-slate-500">{p.pages} pp</span>
                  {p.computable === false && (
                    <span className="ml-1 rounded bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-900" title={p.computable_note || undefined}>
                      payouts can&apos;t be computed exactly
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
        {busy === "upload" && <Loading steps={UPLOAD_STEPS} />}
        {busy === "sample" && <Loading steps={["Loading the cached policy…"]} />}
        {!!policyError && <ErrorBox error={policyError} onRetry={() => lastAction.current()} />}
      </section>

      <section className="card space-y-4" aria-labelledby="profile">
        <h2 id="profile" className="h2">
          2. About you
        </h2>
        <ProfileForm profile={profile} onChange={setProfile} />
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn btn-primary" onClick={loadGaps} disabled={!policy || gapsBusy}>
            Check my gaps
          </button>
          {!policy && <span className="text-sm text-slate-500">Choose a policy first.</span>}
        </div>
      </section>

      {policy && (
        <>
          <section className="space-y-3" aria-labelledby="summary">
            <div className="flex flex-wrap items-center gap-3">
              <h2 id="summary" className="h2">
                {policy.name}
              </h2>
              <span className="text-sm text-slate-500">{policy.pages} pages</span>
              <MetaBadge meta={policy.meta} />
              <button type="button" className="btn btn-secondary ml-auto py-1" onClick={() => pdf.open(policy.policy_id, 1)}>
                Open PDF
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {mainItems.map((s) => (
                <SummaryCard key={s.key} s={s} policyId={policy.policy_id} />
              ))}
            </div>
            {exclusions.length > 0 && (
              <details className="card">
                <summary className="cursor-pointer font-semibold">
                  Exclusions ({exclusions.length}) <span className="text-sm font-normal text-slate-500">— show all</span>
                </summary>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {exclusions.map((s) => (
                    <SummaryCard key={s.key} s={s} policyId={policy.policy_id} />
                  ))}
                </div>
              </details>
            )}
          </section>

          <section className="space-y-3" aria-labelledby="gaps">
            <div className="flex flex-wrap items-center gap-3">
              <h2 id="gaps" className="h2">
                Gap report
              </h2>
              {gaps && (
                <span className="rounded bg-slate-200 px-2 py-0.5 text-sm">
                  Plan: <strong>{gaps.plan}</strong>
                </span>
              )}
              {gaps && <MetaBadge meta={gaps.meta} />}
            </div>
            {gapsBusy && <Loading steps={["Comparing the policy rules with your profile…"]} />}
            {!!gapsError && <ErrorBox error={gapsError} onRetry={loadGaps} />}
            {gaps?.metrics && !gapsBusy && <GapCharts m={gaps.metrics} />}
            {gaps && !gapsBusy && (
              <div className="space-y-2">
                {gaps.gaps.length === 0 && <p className="text-sm text-slate-600">No gaps found for your profile.</p>}
                {[...gaps.gaps]
                  .sort((a, b) => ["high", "medium", "info"].indexOf(a.severity) - ["high", "medium", "info"].indexOf(b.severity))
                  .map((g, i) => {
                    const st = SEVERITY_STYLE[g.severity] || SEVERITY_STYLE.info;
                    return (
                      <article key={i} className={`rounded-xl border p-4 ${st.box}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${st.tag}`}>{st.label}</span>
                          <h3 className="font-semibold">{g.title}</h3>
                        </div>
                        <p className="mt-1 text-sm">{g.detail}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <ClauseChip policyId={policy.policy_id} clause={g.clause} page={g.page} quote={g.quote} />
                          {g.quote && <VerifiedBadge verified={g.verified} />}
                        </div>
                      </article>
                    );
                  })}
              </div>
            )}
          </section>

          <div className="flex justify-end">
            <Link href="/claim" className="btn btn-primary">
              Next: what happened →
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
