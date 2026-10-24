"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { usePdf } from "@/components/PdfModal";
import { ErrorBox, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { PolicyListItem } from "@/lib/types";

const UPLOAD_STEPS = [
  "Uploading the PDF…",
  "Reading the text of every page…",
  "The language model is extracting the coverage rules…",
  "Free-tier calls are paced, so this can take a while…",
  "Verifying every quote against its page…",
];

export default function WalletPage() {
  const { ready, wallet, addPolicy, removePolicy, policy, setPolicy } = useStore();
  const pdf = usePdf();
  const [library, setLibrary] = useState<PolicyListItem[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null); // "upload" | "sample:<id>" | "open:<id>"
  const [confirm, setConfirm] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    setError(null);
    api.listPolicies().then(setLibrary, setError);
  }, []);
  useEffect(load, [load]);

  const byId = (id: string) => library?.find((p) => p.policy_id === id);
  const mine: PolicyListItem[] = wallet.map((id) => byId(id) ?? { policy_id: id, name: id, pages: 0 });
  const samples = (library || []).filter((p) => !wallet.includes(p.policy_id));

  async function upload() {
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    setBusy("upload");
    setError(null);
    try {
      const p = await api.uploadPolicy(f);
      addPolicy(p.policy_id);
      if (!policy) setPolicy(p);
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function addSample(id: string) {
    setBusy(`sample:${id}`);
    setError(null);
    try {
      const p = await api.getPolicy(id);
      addPolicy(id);
      if (!policy) setPolicy(p);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function makeActive(id: string) {
    setBusy(`open:${id}`);
    setError(null);
    try {
      setPolicy(await api.getPolicy(id));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function remove(id: string) {
    setConfirm(null);
    removePolicy(id);
    // Keep an active policy whenever the user still has one.
    const rest = wallet.filter((x) => x !== id);
    if (policy?.policy_id === id && rest.length > 0) await makeActive(rest[0]);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">My policies</h1>
        <p className="mt-1 text-slate-600">
          The policies you own. They are the ones shown on the My policy page, and with two or more a claim is checked against
          all of them to show which pays more. This list lives in your browser and starts empty on each launch.
        </p>
      </div>

      {!!error && <ErrorBox error={error} onRetry={load} />}

      <section className="space-y-3" aria-labelledby="mine">
        <h2 id="mine" className="h2">
          Your policies {ready && <span className="text-base font-normal text-slate-500">({mine.length})</span>}
        </h2>
        {ready && mine.length === 0 && (
          <div className="card text-sm text-slate-600">You have not added a policy yet. Upload a PDF or add a sample below.</div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          {mine.map((p) => {
            const active = policy?.policy_id === p.policy_id;
            const computable = p.computable !== false;
            return (
              <article key={p.policy_id} className={`card flex flex-col gap-2 ${active ? "ring-2 ring-teal-600" : ""}`}>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{p.name}</span>
                    {active && <span className="rounded bg-teal-700 px-1.5 py-0.5 text-xs font-medium text-white">Active</span>}
                  </div>
                  {p.pages > 0 && <span className="text-sm text-slate-500">{p.pages} pages</span>}
                </div>
                {!computable && (
                  <div className="rounded-lg bg-amber-50 p-2 text-sm text-amber-950">
                    <span className="mr-1 rounded bg-amber-400 px-1.5 py-0.5 text-xs font-semibold text-amber-950">
                      Can&apos;t compute payouts
                    </span>
                    {p.computable_note}
                  </div>
                )}
                <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
                  <button type="button" className="btn btn-secondary py-1" onClick={() => pdf.open(p.policy_id, 1)}>
                    Open PDF
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary py-1"
                    disabled={active || busy !== null}
                    onClick={() => makeActive(p.policy_id)}
                  >
                    {active ? "Viewing" : busy === `open:${p.policy_id}` ? "Loading…" : "View summary"}
                  </button>
                  {confirm === p.policy_id ? (
                    <span className="ml-auto flex items-center gap-2 text-sm">
                      Remove?
                      <button
                        type="button"
                        className="btn bg-red-700 py-1 text-white hover:bg-red-800"
                        onClick={() => remove(p.policy_id)}
                      >
                        Yes, remove
                      </button>
                      <button type="button" className="btn btn-secondary py-1" onClick={() => setConfirm(null)}>
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-secondary ml-auto py-1 text-red-800"
                      onClick={() => setConfirm(p.policy_id)}
                      aria-label={`Remove ${p.name} from my policies`}
                    >
                      Remove
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="card space-y-4" aria-labelledby="add">
        <h2 id="add" className="h2">
          Add a policy
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1">
            <label htmlFor="wallet-pdf" className="label">
              Upload a policy wording (PDF with a text layer)
            </label>
            <input
              id="wallet-pdf"
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-200 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-slate-300"
            />
          </div>
          <button type="button" className="btn btn-primary" onClick={upload} disabled={busy !== null}>
            Upload &amp; add
          </button>
        </div>
        {busy === "upload" && <Loading steps={UPLOAD_STEPS} />}
        <div>
          <div className="label">…or add a sample policy we have already read</div>
          {!library && !error ? (
            <p className="text-sm text-slate-500">Loading samples…</p>
          ) : samples.length === 0 ? (
            <p className="text-sm text-slate-500">All available samples are already in your list.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {samples.map((p) => (
                <button
                  key={p.policy_id}
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy !== null}
                  onClick={() => addSample(p.policy_id)}
                >
                  {busy === `sample:${p.policy_id}` ? "Adding…" : `+ ${p.name}`}
                  <span className="text-xs text-slate-500">{p.pages} pp</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      {ready && mine.length > 0 && (
        <div className="card flex flex-wrap items-center gap-3">
          <div className="flex-1 text-sm">
            {mine.length === 1 ? `1 policy: ${mine[0].name}.` : `${mine.length} policies — claims will be compared across them.`}
          </div>
          {policy && (
            <Link href="/" className="btn btn-secondary">
              See active policy
            </Link>
          )}
          <Link href="/claim" className="btn btn-primary">
            Check a claim →
          </Link>
        </div>
      )}
    </div>
  );
}
