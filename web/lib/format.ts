// Indian digit grouping: ₹1,15,000
export function inr(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n < 0 ? "−" : "";
  return `${sign}₹${Math.abs(Math.round(n)).toLocaleString("en-IN")}`;
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export const VERDICT_LABEL: Record<string, string> = {
  COVERED: "Covered",
  PARTIAL: "Partially covered",
  NOT_COVERED: "Not covered",
  NEEDS_REVIEW: "Needs human review",
};

// Tailwind classes per verdict; text/background pairs meet WCAG AA contrast.
export const VERDICT_STYLE: Record<string, string> = {
  COVERED: "bg-emerald-700 text-white",
  PARTIAL: "bg-amber-400 text-amber-950",
  NOT_COVERED: "bg-red-700 text-white",
  NEEDS_REVIEW: "bg-indigo-700 text-white",
};

export const SEVERITY_STYLE: Record<string, { box: string; tag: string; label: string }> = {
  high: { box: "border-red-300 bg-red-50", tag: "bg-red-700 text-white", label: "High" },
  medium: { box: "border-amber-300 bg-amber-50", tag: "bg-amber-400 text-amber-950", label: "Medium" },
  info: { box: "border-sky-200 bg-sky-50", tag: "bg-sky-700 text-white", label: "Info" },
};

export function prettyCategory(c: string): string {
  return c.replace(/_/g, " ").replace(/^\w/, (m) => m.toUpperCase());
}

/** Short label for how a policy's payouts are estimated. */
export function qualityLabel(q?: string | null, computable?: boolean): string | null {
  if (q === "best_case") return "best-case estimates";
  if (q === "terms_only" || (q === undefined && computable === false)) return "payouts can't be computed";
  return null;
}
