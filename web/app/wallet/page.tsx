"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { usePdf } from "@/components/PdfModal";
import { ErrorBox, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { PolicyListItem } from "@/lib/types";

export default function WalletPage() {
  const { ready, wallet, setWallet, policy, setPolicy } = useStore();
  const pdf = usePdf();
  const [library, setLibrary] = useState<PolicyListItem[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [switching, setSwitching] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api.listPolicies().then(setLibrary, setError);
  }, []);
  useEffect(load, [load]);

  const toggle = (id: string) => setWallet(wallet.includes(id) ? wallet.filter((x) => x !== id) : [...wallet, id]);

  async function makeActive(id: string) {
    setSwitching(id);
    try {
      setPolicy(await api.getPolicy(id));
    } catch (e) {
      setError(e);
    } finally {
      setSwitching(null);
    }
  }

  const owned = (library || []).filter((p) => wallet.includes(p.policy_id));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">My policies</h1>
        <p className="mt-1 text-slate-600">
          Tick the policies you own. With two or more, a claim is checked against all of them and we show which one pays
          more — and whether you can claim from both. Your choices stay in this browser only.
        </p>
      </div>

      {!library && !error && <Loading steps={["Loading the policy library…"]} />}
      {!!error && <ErrorBox error={error} onRetry={load} />}

      {library && (
        <div className="grid gap-3 sm:grid-cols-2">
          {library.map((p) => {
            const mine = wallet.includes(p.policy_id);
            const computable = p.computable !== false;
            return (
              <article key={p.policy_id} className={`card flex flex-col gap-2 ${mine ? "ring-2 ring-teal-600" : ""}`}>
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={mine}
                    onChange={() => toggle(p.policy_id)}
                    className="mt-1 h-5 w-5 shrink-0 accent-teal-700"
                    aria-label={`I own ${p.name}`}
                  />
                  <span>
                    <span className="block font-semibold">{p.name}</span>
                    <span className="text-sm text-slate-500">{p.pages} pages</span>
                  </span>
                </label>
                {!computable && (
                  <div className="rounded-lg bg-amber-50 p-2 text-sm text-amber-950">
                    <span className="mr-1 rounded bg-amber-400 px-1.5 py-0.5 text-xs font-semibold text-amber-950">
                      Can&apos;t compute payouts
                    </span>
                    {p.computable_note}
                  </div>
                )}
                <div className="mt-auto flex flex-wrap gap-2 pt-1">
                  <button type="button" className="btn btn-secondary py-1" onClick={() => pdf.open(p.policy_id, 1)}>
                    Open PDF
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary py-1"
                    disabled={policy?.policy_id === p.policy_id || switching !== null}
                    onClick={() => makeActive(p.policy_id)}
                  >
                    {policy?.policy_id === p.policy_id ? "Active policy" : switching === p.policy_id ? "Loading…" : "View summary"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {ready && library && (
        <div className="card flex flex-wrap items-center gap-3">
          <div className="flex-1 text-sm">
            {owned.length === 0 && "No policies ticked yet."}
            {owned.length === 1 && `1 policy in your wallet: ${owned[0].name}.`}
            {owned.length >= 2 && `${owned.length} policies in your wallet — claims will be compared across them.`}
          </div>
          {owned.length >= 1 && policy?.policy_id !== owned[0].policy_id && owned.length === 1 && (
            <button type="button" className="btn btn-secondary" onClick={() => makeActive(owned[0].policy_id)}>
              Use it for claims
            </button>
          )}
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
