"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { NumberField, PedSelect } from "@/components/ProfileForm";
import { ErrorBox, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { Bill, ClaimRequest, PolicyListItem } from "@/lib/types";

const EXAMPLES = [
  {
    label: "Appendix surgery",
    text: "My father had appendix surgery. 3 days in a single AC room at ₹8,000/day. Total bill ₹1.6 lakh.",
  },
  {
    label: "Cataract",
    text: "My mother had cataract surgery on one eye. 1 day in hospital at ₹5,000/day. Bill was ₹60,000.",
  },
  {
    label: "Not sure about history",
    text: "I was admitted for 3 days with appendix pain, room ₹8,000/day, total bill ₹1.6 lakh. I'm not sure if this was diagnosed before my policy started.",
  },
  { label: "No amounts yet", text: "My father had appendix surgery last week." },
];

const BILL_FIELDS: { k: keyof Bill; label: string; hint: string }[] = [
  { k: "room", label: "Room charges", hint: "Room, boarding, nursing" },
  { k: "linked", label: "Associated charges", hint: "Doctor, surgeon, OT, tests" },
  { k: "meds_implants", label: "Medicines & implants", hint: "Pharmacy, implants, stents" },
  { k: "other", label: "Other", hint: "Anything else" },
];

const PROGRESS = [
  "Sending your description…",
  "The language model is extracting the facts…",
  "Free-tier calls are paced, so this can take 20–60 s…",
  "Applying the policy rules in code…",
  "Running the what-if scenarios…",
  "Writing a plain-language explanation…",
  "Still working — thanks for your patience…",
];


export default function ClaimPage() {
  const router = useRouter();
  const { ready, policy, profile, setProfile, wallet, draft, setDraft, job, runClaim } = useStore();
  const { text, bill, showBill, answers, questions, compare } = draft;
  const setText = (t: string) => setDraft((d) => ({ ...d, text: t }));
  const setBill = (b: typeof bill) => setDraft((d) => ({ ...d, bill: b }));
  const setShowBill = (f: (s: boolean) => boolean) => setDraft((d) => ({ ...d, showBill: f(d.showBill) }));
  const setCompare = (v: boolean) => setDraft((d) => ({ ...d, compare: v }));
  const setQuestions = (q: typeof questions) => setDraft((d) => ({ ...d, questions: q }));
  const setAnswers = (a: typeof answers) => setDraft((d) => ({ ...d, answers: a }));
  const busy = job.status === "running";
  const error = job.status === "error" ? job.error : null;
  const prevStatus = useRef(job.status);
  // Go to the verdict when a check that was running while this page was open finishes.
  useEffect(() => {
    if (prevStatus.current === "running" && job.status === "done") router.push("/verdict");
    prevStatus.current = job.status;
  }, [job.status, router]);
  const [library, setLibrary] = useState<PolicyListItem[]>([]);

  useEffect(() => {
    api.listPolicies().then(setLibrary, () => setLibrary([]));
  }, []);

  // Until the library loads, trust the stored wallet; afterwards drop ids the server no longer knows.
  const walletIds = library.length ? wallet.filter((id) => library.some((p) => p.policy_id === id)) : wallet;
  const multi = compare && walletIds.length >= 2;

  function buildRequest(): ClaimRequest {
    const b: Partial<Bill> = {};
    for (const f of BILL_FIELDS) if (bill[f.k] !== null) b[f.k] = bill[f.k] as number;
    const extra: Record<string, unknown> = {};
    // needs_info answers: "bill.x" fields go into the bill, the rest into answers.
    for (const [field, v] of Object.entries(answers)) {
      if (field.startsWith("bill.")) {
        if (v !== null && v !== "") b[field.slice(5) as keyof Bill] = Number(v);
      } else extra[field] = v;
    }
    const req: ClaimRequest = { profile, incident_text: text.trim() };
    if (multi) req.policy_ids = walletIds;
    else req.policy_id = policy?.policy_id;
    if (Object.keys(b).length) req.bill = b;
    if (Object.keys(extra).length) req.answers = extra;
    return req;
  }

  function submit() {
    runClaim(buildRequest());
  }

  if (ready && !policy && walletIds.length < 2) {
    return (
      <div className="card space-y-3">
        <h1 className="h1">What happened</h1>
        <p>First choose your policy so we know which rules apply.</p>
        <Link href="/" className="btn btn-primary">
          Choose a policy
        </Link>
      </div>
    );
  }

  const canSubmit = text.trim().length >= 5 && !busy;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">What happened</h1>
        <p className="mt-1 text-slate-600">
          Describe the hospital stay in your own words. If something important is missing we will ask a short question.
        </p>
      </div>

      <section className="card space-y-3">
        {walletIds.length >= 2 && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} className="h-4 w-4 accent-teal-700" />
            Compare across my {walletIds.length} policies
            <Link href="/wallet" className="text-teal-700 underline">
              edit
            </Link>
          </label>
        )}
        <p className="text-sm text-slate-600">
          {multi ? (
            <>Checking against {walletIds.length} policies from your wallet.</>
          ) : (
            <>
              Policy: <strong>{policy?.name}</strong>
            </>
          )}{" "}
          · Age {profile.insured_age} · Sum insured ₹{profile.sum_insured.toLocaleString("en-IN")} ·{" "}
          <Link href="/" className="text-teal-700 underline">
            edit profile
          </Link>
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField
            id="pam-claim"
            label="Policy age at the time of treatment (months)"
            value={profile.policy_age_months}
            onChange={(n) => setProfile({ ...profile, policy_age_months: n ?? 0 })}
            hint="Waiting periods depend on this"
          />
          <PedSelect
            id="ped-claim"
            label="Any pre-existing conditions?"
            value={profile.ped}
            onChange={(v) => setProfile({ ...profile, ped: v })}
          />
        </div>
      </section>

      <section className="card space-y-3">
        <label htmlFor="incident" className="h2 block">
          Describe the incident
        </label>
        <div className="flex flex-wrap gap-2">
          <span className="text-sm text-slate-500">Examples:</span>
          {EXAMPLES.map((e) => (
            <button
              key={e.label}
              type="button"
              className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:bg-slate-100"
              onClick={() => {
                setText(e.text);
                setQuestions(null);
                setAnswers({});
              }}
            >
              {e.label}
            </button>
          ))}
        </div>
        <textarea
          id="incident"
          rows={4}
          className="input"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setQuestions(null);
            setAnswers({});
          }}
          placeholder="e.g. My father had appendix surgery. 3 days in a single AC room at ₹8,000/day. Total bill ₹1.6 lakh."
        />

        <button type="button" className="text-sm font-medium text-teal-800 underline" onClick={() => setShowBill((s) => !s)}>
          {showBill ? "Hide" : "Add"} an itemised bill (optional)
        </button>
        {showBill && (
          <div className="grid gap-4 rounded-lg bg-slate-50 p-3 sm:grid-cols-2 lg:grid-cols-4">
            {BILL_FIELDS.map((f) => (
              <NumberField
                key={f.k}
                id={`bill-${f.k}`}
                label={f.label}
                hint={f.hint}
                prefix="₹"
                value={bill[f.k]}
                onChange={(n) => setBill({ ...bill, [f.k]: n })}
              />
            ))}
          </div>
        )}
      </section>

      {questions && (
        <section className="card space-y-3 border-amber-300 bg-amber-50" aria-labelledby="qs">
          <h2 id="qs" className="h2">
            A few quick questions
          </h2>
          <p className="text-sm text-slate-700">We need these to compute the estimate. Answer what you can.</p>
          <div className="grid gap-4 sm:grid-cols-2">
            {questions.map((q) =>
              q.type === "boolean" ? (
                <PedSelect
                  key={q.field}
                  id={`q-${q.field}`}
                  label={q.question}
                  value={(answers[q.field] as boolean | null) ?? null}
                  onChange={(v) => setAnswers({ ...answers, [q.field]: v })}
                />
              ) : q.type === "number" ? (
                <NumberField
                  key={q.field}
                  id={`q-${q.field}`}
                  label={q.question}
                  prefix={q.field.startsWith("bill.") ? "₹" : undefined}
                  value={(answers[q.field] as number | null) ?? null}
                  onChange={(n) => setAnswers({ ...answers, [q.field]: n })}
                />
              ) : (
                <div key={q.field}>
                  <label htmlFor={`q-${q.field}`} className="label">
                    {q.question}
                  </label>
                  <input
                    id={`q-${q.field}`}
                    className="input"
                    value={(answers[q.field] as string) ?? ""}
                    onChange={(e) => setAnswers({ ...answers, [q.field]: e.target.value })}
                  />
                </div>
              ),
            )}
          </div>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn btn-primary" onClick={submit} disabled={!canSubmit}>
          {questions ? "Submit answers" : "Check my claim"}
        </button>
        {!text.trim() && <span className="text-sm text-slate-500">Describe what happened first.</span>}
      </div>
      {busy && <Loading steps={PROGRESS} />}
      {!!error && <ErrorBox error={error} onRetry={submit} />}
    </div>
  );
}
