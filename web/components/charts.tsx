"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { inr, prettyCategory } from "@/lib/format";
import type { Counterfactual, GapMetrics, RankedPolicy, ComparisonResult, Verdict } from "@/lib/types";

const TEAL = "#0f766e";
const RED = "#b91c1c";
const AMBER = "#d97706";
const SLATE = "#64748b";
const INDIGO = "#4338ca";
const GREEN = "#047857";
const PALETTE = [TEAL, INDIGO, AMBER, "#be185d", SLATE, GREEN];

const short = (n: number) =>
  n >= 10000000 ? `${(n / 10000000).toFixed(1)}Cr` : n >= 100000 ? `${(n / 100000).toFixed(n % 100000 ? 1 : 0)}L` : n >= 1000 ? `${Math.round(n / 1000)}k` : String(n);

export function ChartCard({
  title,
  note,
  children,
  label,
}: {
  title: string;
  note?: string;
  children: React.ReactNode;
  label: string;
}) {
  return (
    <figure className="card space-y-2" aria-label={label}>
      <figcaption>
        <h3 className="font-semibold">{title}</h3>
        {note && <p className="text-xs text-slate-500">{note}</p>}
      </figcaption>
      <div role="img" aria-label={label}>
        {children}
      </div>
    </figure>
  );
}

const tipMoney = (v: unknown) => inr(typeof v === "number" ? v : Number(v));

const STEP_NAME: Record<string, string> = {
  room_rent: "Room cap",
  proportionate: "Proportionate cut",
  proportionate_meds_implants: "Meds cut",
  proportionate_other: "Other cut",
  sublimit: "Sub-limit",
  copay: "Co-pay",
  sum_insured: "Sum insured cap",
  exclusion: "Exclusion",
  waiting_initial: "Initial wait",
  waiting_ped: "PED wait",
  waiting_specific: "Waiting period",
};

// ------------------------------------------------------------------ verdict
/** Billed → each reduction → payout, built only from the engine trace. */
export function PayoutWaterfall({ v }: { v: Verdict }) {
  if (v.billed === null || v.payout === null) return null;
  const rows: { name: string; base: number; value: number; kind: "total" | "cut" }[] = [];
  let level = v.billed;
  rows.push({ name: "Billed", base: 0, value: v.billed, kind: "total" });
  for (const t of v.trace) {
    if (t.step === "total" || t.before === null || t.after === null) continue;
    const cut = t.before - t.after;
    if (cut > 0) {
      rows.push({ name: STEP_NAME[t.step] || prettyCategory(t.step), base: Math.max(level - cut, 0), value: cut, kind: "cut" });
      level -= cut;
    }
  }
  rows.push({ name: "Payout", base: 0, value: v.payout, kind: "total" });
  return (
    <ChartCard
      title="From bill to payout"
      note="Each red bar is a reduction taken from the calculation steps below."
      label={`Waterfall from billed ${inr(v.billed)} to payout ${inr(v.payout)}`}
    >
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} />
          <YAxis tickFormatter={short} width={48} tick={{ fontSize: 11 }} />
          <Tooltip formatter={tipMoney} />
          <Bar dataKey="base" stackId="a" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="value" stackId="a" isAnimationActive={false}>
            {rows.map((r, i) => (
              <Cell key={i} fill={r.kind === "cut" ? RED : r.name === "Payout" ? TEAL : SLATE} />
            ))}
            <LabelList dataKey="value" position="top" formatter={(x: unknown) => tipMoney(x)} style={{ fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function PaySplit({ v }: { v: Verdict }) {
  if (v.billed === null || v.payout === null || v.billed <= 0) return null;
  const data = [
    { name: "Insurer pays", value: v.payout },
    { name: "You pay", value: Math.max(v.billed - v.payout, 0) },
  ];
  return (
    <ChartCard title="Who pays what" label={`Insurer pays ${inr(v.payout)}, you pay ${inr(v.billed - v.payout)}`}>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={2} isAnimationActive={false}>
            <Cell fill={TEAL} />
            <Cell fill={RED} />
          </Pie>
          <Tooltip formatter={tipMoney} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function WhatIfChart({ payout, cfs }: { payout: number | null; cfs: Counterfactual[] }) {
  if (payout === null || cfs.length === 0) return null;
  const data = [
    { name: "This estimate", payout },
    ...cfs.filter((c) => c.new_payout !== null).map((c) => ({ name: c.change.slice(0, 48), payout: c.new_payout as number })),
  ];
  return (
    <ChartCard title="What-if payouts" note="Each bar re-runs the same calculation with one change." label="Payout under alternative scenarios">
      <ResponsiveContainer width="100%" height={60 + data.length * 44}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 56 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={short} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="name" width={170} tick={{ fontSize: 11 }} />
          <Tooltip formatter={tipMoney} />
          <Bar dataKey="payout" isAnimationActive={false}>
            {data.map((_, i) => (
              <Cell key={i} fill={i === 0 ? SLATE : TEAL} />
            ))}
            <LabelList dataKey="payout" position="right" formatter={(x: unknown) => tipMoney(x)} style={{ fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ------------------------------------------------------------------ gap report
const TONE: Record<string, string> = {
  green: "border-emerald-300 bg-emerald-50 text-emerald-900",
  amber: "border-amber-300 bg-amber-50 text-amber-900",
  indigo: "border-indigo-300 bg-indigo-50 text-indigo-900",
  slate: "border-slate-300 bg-white text-slate-900",
};

function Tile({ label, value, note, tone }: { label: string; value: string; note: string; tone: keyof typeof TONE }) {
  return (
    <div className={`rounded-xl border p-3 ${TONE[tone]}`}>
      <div className="text-xs font-medium uppercase tracking-wide opacity-80">{label}</div>
      <div className="mt-0.5 text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-xs opacity-80">{note}</div>
    </div>
  );
}

export function GapCharts({ m }: { m: GapMetrics }) {
  const room = m.room && m.room.preferred_per_day
    ? [
        { name: "Policy cap", value: m.room.cap_per_day },
        { name: "Your preferred room", value: m.room.preferred_per_day },
      ]
    : null;
  const sm = m.summary;
  const typical = (m.typical_claims ?? []).map((c) => ({ name: prettyCategory(c.category), Billed: c.billed, Payout: c.payout, verdict: c.verdict }));
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {sm && (
        <div className="grid grid-cols-2 gap-3 md:col-span-2 lg:grid-cols-4">
          <Tile
            label="Co-payment"
            value={sm.copay_percent > 0 ? `${sm.copay_percent}%` : "None"}
            note={sm.copay_percent > 0 ? sm.copay_condition || "of every eligible claim" : "You pay no fixed share"}
            tone={sm.copay_percent > 0 ? "amber" : "green"}
          />
          <Tile
            label="Longest waiting period"
            value={sm.longest_wait_months ? `${sm.longest_wait_months} mo` : "None"}
            note={sm.longest_wait_months ? "before some conditions are paid" : `none on the ${sm.plan ?? "this"} plan`}
            tone={sm.longest_wait_months ? "amber" : "green"}
          />
          <Tile label="Sub-limits" value={String(sm.sublimits)} note="treatments with a fixed cap" tone={sm.sublimits ? "indigo" : "green"} />
          <Tile label="Listed exclusions" value={String(sm.exclusions)} note="not covered at all" tone="slate" />
        </div>
      )}
      {typical.length > 0 && (
        <div className="md:col-span-2">
          <ChartCard
            title="What typical claims would pay on this policy"
            note={`Illustrative bill sizes, your profile and a policy age of ${m.policy_age_months} months. Zero bars are waiting periods or exclusions.`}
            label="Billed amount and estimated payout for five typical claims"
          >
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={typical} margin={{ top: 16, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={short} width={48} tick={{ fontSize: 11 }} />
                <Tooltip formatter={tipMoney} />
                <Legend />
                <Bar dataKey="Billed" fill="#cbd5e1" isAnimationActive={false} />
                <Bar dataKey="Payout" fill={TEAL} isAnimationActive={false}>
                  {typical.map((t, i) => (
                    <Cell key={i} fill={t.verdict === "NOT_COVERED" ? RED : t.verdict === "PARTIAL" ? AMBER : t.verdict === "NEEDS_REVIEW" ? INDIGO : GREEN} />
                  ))}
                  <LabelList dataKey="Payout" position="top" formatter={(x: unknown) => (Number(x) ? tipMoney(x) : "₹0")} style={{ fontSize: 11 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}
      {room && m.room && (
        <ChartCard
          title="Room rent vs cap (per day)"
          note={m.room.payable_pct < 100 ? `Above the cap, associated charges are paid at ${m.room.payable_pct}%.` : "Your room is within the cap."}
          label={`Room cap ${inr(m.room.cap_per_day)} per day versus preferred ${inr(m.room.preferred_per_day)}`}
        >
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={room} margin={{ top: 16, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={short} width={44} tick={{ fontSize: 11 }} />
              <Tooltip formatter={tipMoney} />
              <Bar dataKey="value" isAnimationActive={false}>
                <Cell fill={TEAL} />
                <Cell fill={m.room.payable_pct < 100 ? RED : GREEN} />
                <LabelList dataKey="value" position="top" formatter={(x: unknown) => tipMoney(x)} style={{ fontSize: 11 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}
      {m.waiting.length > 0 && (
        <ChartCard
          title="Waiting periods (months)"
          note={`Dashed line = your policy age (${m.policy_age_months} months). Bars to the right of it are still blocking.`}
          label="Waiting periods in months compared with policy age"
        >
          <ResponsiveContainer width="100%" height={60 + m.waiting.length * 40}>
            <BarChart data={m.waiting} layout="vertical" margin={{ left: 8, right: 28 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} domain={[0, (max: number) => Math.max(max, m.policy_age_months + 6)]} />
              <YAxis type="category" dataKey="label" width={150} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: unknown) => `${v} months`} />
              <Bar dataKey="months" isAnimationActive={false}>
                {m.waiting.map((w, i) => (
                  <Cell key={i} fill={w.months > m.policy_age_months ? AMBER : GREEN} />
                ))}
                <LabelList dataKey="months" position="right" style={{ fontSize: 11 }} />
              </Bar>
              <ReferenceLine x={m.policy_age_months} stroke={INDIGO} strokeDasharray="5 4" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}
      {m.sublimits.length > 0 && (
        <ChartCard
          title="Sub-limits for your sum insured"
          note="Maximum the policy pays for these treatments, whatever the bill."
          label="Sub-limit caps in rupees"
        >
          <ResponsiveContainer width="100%" height={60 + m.sublimits.length * 40}>
            <BarChart data={m.sublimits} layout="vertical" margin={{ left: 8, right: 64 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tickFormatter={short} tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="label" width={170} tick={{ fontSize: 11 }} />
              <Tooltip formatter={tipMoney} />
              <Bar dataKey="cap_inr" fill={INDIGO} isAnimationActive={false}>
                <LabelList dataKey="cap_inr" position="right" formatter={(x: unknown) => tipMoney(x)} style={{ fontSize: 11 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ comparison / recommender
export function ComparisonChart({ results }: { results: ComparisonResult[] }) {
  const data = results.map((r) => ({
    name: r.name.replace(/\(sample\)/i, "").trim().slice(0, 30),
    Billed: r.verdict.billed ?? 0,
    Payout: r.verdict.payout ?? 0,
    review: r.verdict.payout === null,
  }));
  return (
    <ChartCard
      title="Payout by policy for this claim"
      note={data.some((d) => d.review) ? "Policies needing review show no payout bar." : undefined}
      label="Billed amount and estimated payout for each policy"
    >
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 16, right: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={short} width={48} tick={{ fontSize: 11 }} />
          <Tooltip formatter={tipMoney} />
          <Legend />
          <Bar dataKey="Billed" fill="#cbd5e1" isAnimationActive={false} />
          <Bar dataKey="Payout" fill={TEAL} isAnimationActive={false}>
            <LabelList dataKey="Payout" position="top" formatter={(x: unknown) => (Number(x) ? tipMoney(x) : "")} style={{ fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

const SCORE_PARTS: [string, string, string][] = [
  ["payout", "Simulated payout (70)", TEAL],
  ["waiting", "Waiting periods (10)", AMBER],
  ["copay", "Co-pay (10)", INDIGO],
  ["room_cap", "Room cap (5)", "#be185d"],
  ["exclusions", "Exclusions (5)", SLATE],
];

export function ScoreChart({ ranked }: { ranked: RankedPolicy[] }) {
  const rows = ranked
    .filter((r) => r.score !== null && r.score_breakdown)
    .map((r) => ({ name: r.name.replace(/\(sample\)/i, "").trim().slice(0, 30), ...r.score_breakdown }));
  if (rows.length === 0) return null;
  return (
    <ChartCard
      title="Score breakdown"
      note="Points out of 100 by rubric part, all computed in code."
      label="Stacked score by rubric part for each policy"
    >
      <ResponsiveContainer width="100%" height={80 + rows.length * 56}>
        <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="name" width={160} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          {SCORE_PARTS.map(([k, label, color]) => (
            <Bar key={k} dataKey={k} name={label} stackId="s" fill={color} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function ScenarioChart({ ranked }: { ranked: RankedPolicy[] }) {
  const comp = ranked.filter((r) => r.computable && r.scenario_results.length > 0);
  if (comp.length === 0) return null;
  const cats = comp[0].scenario_results.map((s) => s.category);
  const data = cats.map((c) => {
    const row: Record<string, string | number> = { name: prettyCategory(c) };
    comp.forEach((p) => {
      row[p.name] = p.scenario_results.find((s) => s.category === c)?.payout ?? 0;
    });
    return row;
  });
  return (
    <ChartCard
      title="Simulated payout per likely claim"
      note="Each claim is run as if the policy were bought today, so waiting periods can reduce it to zero."
      label="Simulated payout for each listed claim, grouped by policy"
    >
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 16, right: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={short} width={48} tick={{ fontSize: 11 }} />
          <Tooltip formatter={tipMoney} />
          <Legend />
          {comp.map((p, i) => (
            <Bar key={p.policy_id} dataKey={p.name} fill={PALETTE[i % PALETTE.length]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ------------------------------------------------------------------ eval
const METRIC_LABEL: Record<string, string> = {
  verdict_accuracy: "Verdict accuracy",
  payout_within_1_pct: "Payout within 1%",
  citation_correctness: "Citation correctness",
  quote_verified_pct: "Quotes verified",
  extraction_accuracy: "Extraction accuracy",
  abstention_precision: "Abstention precision",
  abstention_recall: "Abstention recall",
  confident_wrong_rate: "Confident-wrong rate (lower is better)",
};

export function MetricsChart({ metrics }: { metrics: Record<string, number | null> }) {
  const data = Object.entries(METRIC_LABEL)
    .filter(([k]) => metrics[k] !== null && metrics[k] !== undefined)
    .map(([k, label]) => ({ name: label, pct: Math.round((metrics[k] as number) * 1000) / 10, bad: k === "confident_wrong_rate" }));
  return (
    <ChartCard title="Metrics at a glance" note="Percent; higher is better except the confident-wrong rate." label="Evaluation metrics as percentages">
      <ResponsiveContainer width="100%" height={60 + data.length * 36}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 40 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="name" width={210} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: unknown) => `${v}%`} />
          <Bar dataKey="pct" isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.bad ? RED : TEAL} />
            ))}
            <LabelList dataKey="pct" position="right" formatter={(x: unknown) => `${x}%`} style={{ fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function PipelineVsBaseline({
  metrics,
  baseline,
}: {
  metrics: Record<string, number | null>;
  baseline: Record<string, number | string | null>;
}) {
  const keys: [string, string][] = [
    ["verdict_accuracy", "Verdict accuracy"],
    ["abstention_recall", "Abstention recall"],
  ];
  const data = keys
    .filter(([k]) => typeof baseline[k] === "number" || typeof metrics[k] === "number")
    .map(([k, label]) => ({
      name: label,
      PoliSure: Math.round(((metrics[k] as number) ?? 0) * 1000) / 10,
      "Plain LLM": Math.round((((baseline[k] as number) ?? 0) as number) * 1000) / 10,
    }));
  if (data.length === 0) return null;
  return (
    <ChartCard title="PoliSure vs plain LLM" note="Same scenarios; the plain LLM gets the policy text and the claim and answers directly." label="Pipeline versus baseline metrics">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 16, right: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} unit="%" width={44} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: unknown) => `${v}%`} />
          <Legend />
          <Bar dataKey="PoliSure" fill={TEAL} isAnimationActive={false} />
          <Bar dataKey="Plain LLM" fill={AMBER} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

const ORDER = ["COVERED", "PARTIAL", "NOT_COVERED", "NEEDS_REVIEW"];

/** Confusion matrix as a shaded grid (diagonal = correct). */
export function ConfusionHeatmap({ confusion }: { confusion: Record<string, Record<string, number>> }) {
  const max = Math.max(1, ...ORDER.flatMap((a) => ORDER.map((p) => confusion[a]?.[p] ?? 0)));
  return (
    <ChartCard title="Confusion matrix" note="Rows = expected verdict, columns = predicted. Green diagonal = correct." label="Confusion matrix of expected versus predicted verdicts">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-separate border-spacing-1 text-center text-sm">
          <thead>
            <tr>
              <th className="text-left text-xs font-medium text-slate-500">expected ↓ / predicted →</th>
              {ORDER.map((p) => (
                <th key={p} className="text-xs font-medium text-slate-600">
                  {p.replace("_", " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ORDER.map((a) => (
              <tr key={a}>
                <th className="text-left text-xs font-medium text-slate-600">{a.replace("_", " ")}</th>
                {ORDER.map((p) => {
                  const n = confusion[a]?.[p] ?? 0;
                  const diag = a === p;
                  const alpha = n === 0 ? 0 : 0.2 + 0.8 * (n / max);
                  const bg = diag ? `rgba(4,120,87,${alpha})` : `rgba(185,28,28,${alpha})`;
                  return (
                    <td key={p} className="rounded py-3 font-semibold tabular-nums" style={{ background: n ? bg : "#f1f5f9", color: n && alpha > 0.55 ? "#fff" : "#0f172a" }}>
                      {n}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}
