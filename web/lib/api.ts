import type {
  ClaimRequest,
  ClaimResponse,
  EvalReport,
  AskResponse,
  GapsResponse,
  Policy,
  PolicyListItem,
  Profile,
  RecommendRequest,
  RecommendResponse,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  code: string;
  detail?: string;
  constructor(status: number, code: string, detail?: string) {
    super(detail || code);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "network", `Could not reach the server at ${API_URL}. Is it running?`);
  }
  if (!res.ok) {
    let code = `http_${res.status}`;
    let detail: string | undefined;
    try {
      const body = await res.json();
      if (typeof body?.error === "string") code = body.error;
      if (typeof body?.detail === "string") detail = body.detail;
      else if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, detail);
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  session: () => request<{ boot_id: string }>("/session"),
  listPolicies: () => request<PolicyListItem[]>("/policies"),
  getPolicy: (id: string) => request<Policy>(`/policies/${encodeURIComponent(id)}`),
  uploadPolicy: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Policy>("/policies", { method: "POST", body: fd });
  },
  gaps: (id: string, p: Profile) => {
    const q = new URLSearchParams({
      insured_age: String(p.insured_age),
      sum_insured: String(p.sum_insured),
      preferred_room_rent_per_day: String(p.preferred_room_rent_per_day),
      policy_age_months: String(p.policy_age_months),
    });
    // ped=null ("don't know") is sent by omitting the parameter.
    if (p.ped !== null) q.set("ped", String(p.ped));
    return request<GapsResponse>(`/policies/${encodeURIComponent(id)}/gaps?${q}`);
  },
  checkClaim: (body: ClaimRequest) => request<ClaimResponse>("/claims/check", json(body)),
  recommend: (body: RecommendRequest) => request<RecommendResponse>("/policies/recommend", json(body)),
  ask: (id: string, question: string, history: { role: string; content: string }[]) =>
    request<AskResponse>(`/policies/${encodeURIComponent(id)}/ask`, json({ question, history })),
  evalLatest: () => request<EvalReport>("/eval/latest"),
};

export const pdfUrl = (policyId: string, page?: number | null) =>
  `${API_URL}/policies/${encodeURIComponent(policyId)}/pdf${page ? `#page=${page}` : ""}`;

export function friendlyError(e: unknown): { title: string; body: string; retry: boolean } {
  if (e instanceof ApiError) {
    if (e.code === "llm_unavailable" || e.status === 503)
      return {
        title: "The AI service is busy right now",
        body: "The free model quota is paced or temporarily unavailable. Wait a minute and try again. Your inputs are kept.",
        retry: true,
      };
    if (e.code === "no_report")
      return { title: "No evaluation report yet", body: "Run the eval script on the backend, then reload this page.", retry: false };
    if (e.code === "unknown_policy" || e.status === 404)
      return { title: "Policy not found", body: "The server no longer knows this policy. Upload it again or pick a sample.", retry: false };
    if (e.code === "network") return { title: "Server unreachable", body: e.detail || e.message, retry: true };
    if (e.status === 400) return { title: "That didn't work", body: e.code !== "http_400" ? e.code : e.detail || "Bad request.", retry: false };
    return { title: `Server error (${e.status})`, body: e.detail || e.code, retry: true };
  }
  return { title: "Something went wrong", body: String(e), retry: true };
}
