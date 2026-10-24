// Types mirror CONTRACT.md exactly. Money is integer rupees.

export type Meta = {
  cached: boolean;
  providers_used: string[];
  model_note: string | null;
};

export type Profile = {
  insured_age: number;
  sum_insured: number;
  ped: boolean | null;
  policy_age_months: number;
  preferred_room_rent_per_day: number;
};

export type SummaryItem = {
  key: string;
  label: string;
  summary: string;
  clause: string;
  page: number | null;
  quote: string;
  verified: boolean;
};

export type Policy = {
  policy_id: string;
  name: string;
  pages: number;
  summary_items: SummaryItem[];
  meta: Meta;
};

export type PolicyListItem = {
  policy_id: string;
  name: string;
  pages: number;
  computable?: boolean;
  computable_note?: string | null;
};

export type Severity = "high" | "medium" | "info";

export type Gap = {
  severity: Severity;
  title: string;
  detail: string;
  clause: string;
  page: number | null;
  quote: string;
  verified: boolean;
};

export type GapMetrics = {
  room: { cap_per_day: number; preferred_per_day: number | null; payable_pct: number; proportionate: boolean } | null;
  waiting: { label: string; months: number; detail?: string }[];
  sublimits: { label: string; cap_inr: number }[];
  policy_age_months: number;
};

export type GapsResponse = { plan: string; gaps: Gap[]; metrics?: GapMetrics; meta: Meta };

export type Bill = {
  room: number;
  linked: number;
  meds_implants: number;
  other: number;
};

export type Question = {
  field: string;
  question: string;
  type: "number" | "boolean" | "text" | string;
};

export type VerdictKind = "COVERED" | "PARTIAL" | "NOT_COVERED" | "NEEDS_REVIEW";

export type TraceStep = {
  step: string;
  label: string;
  before: number | null;
  after: number | null;
  clause: string;
  page: number | null;
};

export type Citation = { clause: string; page: number | null; quote: string; verified: boolean };

export type Counterfactual = { change: string; new_payout: number | null; delta: number | null };

export type Verdict = {
  verdict: VerdictKind;
  billed: number | null;
  payout: number | null;
  trace: TraceStep[];
  citations: Citation[];
  counterfactuals: Counterfactual[];
  why: string;
  next_steps: string[];
  abstain_reason: string | null;
  disclaimer: string;
};

export type ComparisonResult = {
  policy_id: string;
  name: string;
  computable: boolean;
  verdict: Verdict;
};

export type Combined = {
  possible: boolean;
  total_payout: number | null;
  split: { policy_id: string; payout: number }[];
  note: string;
};

export type Comparison = {
  results: ComparisonResult[];
  recommended_policy_id: string | null;
  recommendation_reason: string;
  combined: Combined | null;
};

export type ClaimRequest = {
  policy_id?: string;
  policy_ids?: string[];
  profile: Profile;
  incident_text: string;
  bill?: Partial<Bill>;
  answers?: Record<string, unknown>;
};

export type ClaimResponse =
  | { status: "needs_info"; questions: Question[]; meta: Meta }
  | { status: "done"; verdict: Verdict; comparison?: Comparison | null; meta: Meta };

export type RecommendRequest = {
  profile: Profile;
  likely_claims: string[];
  assumed_bills?: Record<string, number>;
  annual_premiums?: Record<string, number>;
  policy_ids?: string[];
};

export type ScenarioResult = {
  category: string;
  billed: number | null;
  payout: number | null;
  verdict: VerdictKind;
  note?: string | null;
};

export type Reason = {
  text: string;
  clause?: string | null;
  page?: number | null;
  quote?: string | null;
  verified?: boolean | null;
};

export type RankedPolicy = {
  policy_id: string;
  name: string;
  computable: boolean;
  score: number | null;
  scenario_results: ScenarioResult[];
  reasons: Reason[];
  premium_note?: string | null;
  score_breakdown?: Record<string, number>;
  total_simulated_payout?: number;
};

export type RecommendResponse = {
  ranked: RankedPolicy[];
  best_policy_id: string | null;
  why: string;
  assumptions: string[];
  disclaimer: string;
  meta: Meta;
};

export type EvalReport = {
  generated_at: string;
  models: Record<string, string>;
  policy: string;
  n_scenarios: number;
  split: string;
  scenarios_note?: string | null;
  metrics: Record<string, number | null>;
  confusion: Record<string, Record<string, number>>;
  baseline: (Record<string, number | string | null> & { note?: string }) | null;
  cross_policy_extraction: { policy: string; extraction_accuracy: number | null }[] | null;
};

export type AskCitation = { clause: string; page: number; quote: string; verified: boolean };

export type AskResponse = {
  answer: string;
  citations: AskCitation[];
  needs_calculation: boolean;
  out_of_scope: boolean;
  note: string | null;
  meta: Meta;
};
