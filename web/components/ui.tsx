"use client";

import { useEffect, useState } from "react";
import { friendlyError } from "@/lib/api";
import { VERDICT_LABEL, VERDICT_STYLE } from "@/lib/format";
import type { Meta } from "@/lib/types";
import { usePdf } from "./PdfModal";

export function MetaBadge({ meta }: { meta?: Meta | null }) {
  if (!meta) return null;
  const providers = meta.providers_used?.length ? meta.providers_used.join(" + ") : "none";
  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-xs" title={meta.model_note || undefined}>
      {meta.cached && <span className="rounded bg-slate-700 px-1.5 py-0.5 font-medium text-white">cached</span>}
      <span className="rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 text-slate-700">via {providers}</span>
      {meta.model_note && <span className="text-slate-500">{meta.model_note}</span>}
    </span>
  );
}

export function VerifiedBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-800" title="Quote found on this page by code">
      ✓ verified
    </span>
  ) : (
    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900" title="Quote not found on the page; not used for money">
      ! unverified
    </span>
  );
}

/** Clause + page chip that opens the policy PDF at that page. */
export function ClauseChip({
  policyId,
  clause,
  page,
  quote,
}: {
  policyId?: string | null;
  clause?: string | null;
  page?: number | null;
  quote?: string | null;
}) {
  const pdf = usePdf();
  const hasClause = clause && clause !== "—";
  if (!hasClause && !page) return <span className="text-xs text-slate-400">—</span>;
  const text = `${hasClause ? `§ ${clause}` : "Policy"}${page ? ` · p.${page}` : ""}`;
  if (!policyId || !page)
    return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{text}</span>;
  return (
    <button
      type="button"
      onClick={() => pdf.open(policyId, page, quote || undefined)}
      className="rounded-full bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-800 ring-1 ring-teal-200 hover:bg-teal-100"
      title="Open the policy PDF at this page"
      aria-label={`${text}: open the policy PDF at this page`}
    >
      {text} ↗
    </button>
  );
}

export function VerdictBadge({ verdict, size = "lg" }: { verdict: string; size?: "lg" | "sm" }) {
  const cls = VERDICT_STYLE[verdict] || "bg-slate-600 text-white";
  return (
    <span
      className={`inline-block rounded-lg font-bold uppercase tracking-wide ${cls} ${
        size === "lg" ? "px-4 py-2 text-xl" : "px-2 py-0.5 text-xs"
      }`}
    >
      {VERDICT_LABEL[verdict] || verdict}
    </span>
  );
}

const DEFAULT_STEPS = [
  "Sending your request…",
  "Reading the policy wording…",
  "The language model is extracting facts…",
  "Free-tier calls are paced, so this can take a while…",
  "Computing the numbers in code…",
  "Checking quotes against the PDF pages…",
  "Still working — thanks for your patience…",
];

/** Loading state that tolerates slow, paced calls: elapsed time plus progress text. */
export function Loading({ steps = DEFAULT_STEPS, label }: { steps?: string[]; label?: string }) {
  const [t, setT] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setT((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const idx = Math.min(Math.floor(t / 4), steps.length - 1);
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3 rounded-xl border border-teal-200 bg-teal-50 p-4">
      <span className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-teal-700 border-t-transparent" />
      <div className="text-sm">
        <div className="font-medium text-teal-900">{label || steps[idx]}</div>
        <div className="text-teal-800/80">{label ? steps[idx] + " · " : ""}{t}s elapsed</div>
      </div>
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = friendlyError(error);
  return (
    <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm">
      <div className="font-semibold text-red-900">{e.title}</div>
      <div className="mt-1 text-red-800">{e.body}</div>
      {e.retry && onRetry && (
        <button type="button" onClick={onRetry} className="btn btn-secondary mt-3">
          Try again
        </button>
      )}
    </div>
  );
}

export function Disclaimer({ text }: { text?: string }) {
  return (
    <div className="rounded-lg border border-slate-300 bg-slate-100 px-4 py-3 text-sm text-slate-800">
      <strong>Disclaimer:</strong> {text || "Estimates the insurer's likely decision; not a legal ruling."}
    </div>
  );
}

export function Quote({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  return <blockquote className="border-l-4 border-slate-300 pl-3 text-sm italic text-slate-600">“{children}”</blockquote>;
}
