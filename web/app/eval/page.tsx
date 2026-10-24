"use client";

import { MetricsChart, PipelineVsBaseline } from "@/components/charts";
import { useCallback, useEffect, useState } from "react";
import { Disclaimer, ErrorBox, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { inr, pct, VERDICT_LABEL } from "@/lib/format";
import type { EvalReport } from "@/lib/types";

const CLASSES = ["COVERED", "PARTIAL", "NOT_COVERED", "NEEDS_REVIEW"];

type MetricDef = { key: string; label: string; kind: "pct" | "inr"; better: "high" | "low"; help: string };
const METRICS: MetricDef[] = [
  { key: "verdict_accuracy", label: "Verdict accuracy", kind: "pct", better: "high", help: "4-class verdict matches the label" },
  { key: "payout_mae_inr", label: "Payout error (MAE)", kind: "inr", better: "low", help: "Mean absolute error in rupees" },
  { key: "payout_within_1_pct", label: "Payout exact (±₹1)", kind: "pct", better: "high", help: "Share of payouts within ₹1" },
  { key: "citation_correctness", label: "Citation correctness", kind: "pct", better: "high", help: "Cited clauses in the expected set" },
  { key: "quote_verified_pct", label: "Quotes verified", kind: "pct", better: "high", help: "Quotes found on the cited page by code" },
  { key: "extraction_accuracy", label: "Clause extraction", kind: "pct", better: "high", help: "Coverage values vs gold" },
  { key: "abstention_precision", label: "Abstention precision", kind: "pct", better: "high", help: "NEEDS_REVIEW when it should" },
  { key: "abstention_recall", label: "Abstention recall", kind: "pct", better: "high", help: "Ambiguous cases caught" },
  { key: "confident_wrong_rate", label: "Confident & wrong", kind: "pct", better: "low", help: "Wrong verdict without abstaining" },
];

const fmt = (kind: MetricDef["kind"], v: unknown) =>
  typeof v !== "number" ? "—" : kind === "inr" ? inr(v) : pct(v);

export default function EvalPage() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(true);

  const load = useCallback(() => {
    setBusy(true);
    setError(null);
    api
      .evalLatest()
      .then(setReport, setError)
      .finally(() => setBusy(false));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="h1">Evaluation</h1>
        <p className="mt-1 text-slate-600">How often the estimate matches hand-labelled scenarios, compared with a plain-LLM baseline.</p>
      </div>
      {busy && <Loading steps={["Loading the latest report…"]} />}
      {!!error && <ErrorBox error={error} onRetry={load} />}
      {report && (
        <>
          <section className="card text-sm">
            <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              <div>
                <dt className="text-slate-500">Policy</dt>
                <dd className="font-medium">{report.policy}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Scenarios</dt>
                <dd className="font-medium">
                  {report.n_scenarios} ({report.split} split)
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Models</dt>
                <dd className="font-medium">
                  {Object.entries(report.models)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(" · ")}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Generated</dt>
                <dd className="font-medium">{new Date(report.generated_at).toLocaleString()}</dd>
              </div>
            </dl>
            {report.scenarios_note && <p className="mt-3 rounded bg-amber-50 p-2 text-amber-950">{report.scenarios_note}</p>}
          </section>

          <section className="space-y-2">
            <h2 className="h2">Metrics</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {METRICS.filter((m) => m.key in report.metrics).map((m) => {
                const base = report.baseline?.[m.key];
                return (
                  <div key={m.key} className="card">
                    <div className="text-sm text-slate-500" title={m.help}>
                      {m.label}
                    </div>
                    <div className="text-2xl font-semibold tabular-nums">{fmt(m.kind, report.metrics[m.key])}</div>
                    {typeof base === "number" && (
                      <div className="text-xs text-slate-500">baseline {fmt(m.kind, base)}</div>
                    )}
                    <div className="mt-1 text-xs text-slate-400">{m.better === "high" ? "higher is better" : "lower is better"}</div>
                  </div>
                );
              })}
              {Object.keys(report.metrics)
                .filter((k) => !METRICS.some((m) => m.key === k))
                .map((k) => {
                  const v = report.metrics[k];
                  return (
                    <div key={k} className="card">
                      <div className="text-sm text-slate-500">{k.replace(/_/g, " ")}</div>
                      <div className="text-2xl font-semibold tabular-nums">
                        {typeof v === "number" ? (v <= 1 ? pct(v) : v.toLocaleString("en-IN")) : "—"}
                      </div>
                    </div>
                  );
                })}
            </div>
          </section>

          <MetricsChart metrics={report.metrics} />
          {report.baseline && <PipelineVsBaseline metrics={report.metrics} baseline={report.baseline} />}
          {report.baseline && (
            <section className="card space-y-2">
              <h2 className="h2">Pipeline vs baseline</h2>
              {report.baseline.note && <p className="text-sm text-slate-600">Baseline: {String(report.baseline.note)}</p>}
              <div className="overflow-x-auto">
                <table className="w-full min-w-[420px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-slate-500">
                      <th className="py-2 pr-3 font-medium">Metric</th>
                      <th className="py-2 pr-3 text-right font-medium">PoliSure</th>
                      <th className="py-2 text-right font-medium">Plain LLM</th>
                    </tr>
                  </thead>
                  <tbody>
                    {METRICS.filter((m) => typeof report.baseline?.[m.key] === "number").map((m) => (
                      <tr key={m.key} className="border-b border-slate-100">
                        <td className="py-2 pr-3">{m.label}</td>
                        <td className="py-2 pr-3 text-right font-semibold tabular-nums">{fmt(m.kind, report.metrics[m.key])}</td>
                        <td className="py-2 text-right tabular-nums">{fmt(m.kind, report.baseline?.[m.key])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="card space-y-2">
            <h2 className="h2">Confusion matrix</h2>
            <p className="text-xs text-slate-500">Rows: expected verdict · columns: predicted verdict</p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-center text-sm">
                <thead>
                  <tr className="text-slate-500">
                    <th className="py-2 text-left font-medium">Expected ↓ / Predicted →</th>
                    {CLASSES.map((c) => (
                      <th key={c} className="py-2 font-medium">
                        {VERDICT_LABEL[c]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {CLASSES.map((row) => (
                    <tr key={row} className="border-t border-slate-100">
                      <th className="py-2 text-left font-medium">{VERDICT_LABEL[row]}</th>
                      {CLASSES.map((col) => {
                        const n = report.confusion?.[row]?.[col] ?? 0;
                        return (
                          <td
                            key={col}
                            className={`py-2 tabular-nums ${
                              n === 0 ? "text-slate-300" : row === col ? "bg-emerald-100 font-semibold text-emerald-900" : "bg-red-50 text-red-900"
                            }`}
                          >
                            {n}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {!!report.cross_policy_extraction?.length && (
            <section className="card space-y-2">
              <h2 className="h2">Cross-policy extraction</h2>
              <p className="text-sm text-slate-600">Clause extraction on policies the pipeline was not tuned on.</p>
              <ul className="text-sm">
                {report.cross_policy_extraction.map((x) => (
                  <li key={x.policy} className="flex justify-between border-b border-slate-100 py-2">
                    <span>{x.policy}</span>
                    <span className="font-semibold tabular-nums">{pct(x.extraction_accuracy)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <Disclaimer />
        </>
      )}
    </div>
  );
}
