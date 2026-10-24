"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Bill, ClaimRequest, ClaimResponse, GapsResponse, Policy, Profile, Question } from "./types";

// Browser storage can throw (private mode, blocked site data); every access is guarded.
export function loadLS<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function saveLS(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

export const DEFAULT_PROFILE: Profile = {
  insured_age: 45,
  sum_insured: 500000,
  ped: false,
  policy_age_months: 24,
  preferred_room_rent_per_day: 8000,
};

export type ClaimRun = { request: ClaimRequest; response: Extract<ClaimResponse, { status: "done" }> };

export type ClaimDraft = {
  text: string;
  bill: Record<keyof Bill, number | null>;
  showBill: boolean;
  compare: boolean;
  answers: Record<string, number | boolean | string | null>;
  questions: Question[] | null;
};
export const EMPTY_DRAFT: ClaimDraft = {
  text: "",
  bill: { room: null, linked: null, meds_implants: null, other: null },
  showBill: false,
  compare: true,
  answers: {},
  questions: null,
};
// A claim check can take a while; it runs in the store so it survives page navigation.
export type ClaimJob = { status: "idle" | "running" | "done" | "error"; startedAt: number | null; error: unknown };

type Store = {
  draft: ClaimDraft;
  setDraft: (f: (d: ClaimDraft) => ClaimDraft) => void;
  job: ClaimJob;
  runClaim: (req: ClaimRequest) => void;
  ackJob: () => void;
  ready: boolean;
  profile: Profile;
  setProfile: (p: Profile) => void;
  policy: Policy | null;
  setPolicy: (p: Policy | null) => void;
  gaps: GapsResponse | null;
  setGaps: (g: GapsResponse | null) => void;
  wallet: string[];
  setWallet: (ids: string[]) => void;
  claim: ClaimRun | null;
  setClaim: (c: ClaimRun | null) => void;
};

const Ctx = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [profile, setProfileState] = useState<Profile>(DEFAULT_PROFILE);
  const [policy, setPolicyState] = useState<Policy | null>(null);
  const [gaps, setGaps] = useState<GapsResponse | null>(null);
  const [wallet, setWalletState] = useState<string[]>([]);
  const [claim, setClaimState] = useState<ClaimRun | null>(null);
  const [draft, setDraftState] = useState<ClaimDraft>(EMPTY_DRAFT);
  const [job, setJob] = useState<ClaimJob>({ status: "idle", startedAt: null, error: null });
  const runId = useRef(0);

  useEffect(() => {
    setProfileState({ ...DEFAULT_PROFILE, ...loadLS<Partial<Profile>>("polisure.profile", {}) });
    setPolicyState(loadLS<Policy | null>("polisure.policy", null));
    setWalletState(loadLS<string[]>("polisure.wallet", []));
    setClaimState(loadLS<ClaimRun | null>("polisure.claim", null));
    const d = loadLS<Partial<ClaimDraft>>("polisure.draft", {});
    setDraftState({ ...EMPTY_DRAFT, text: d.text ?? "", bill: { ...EMPTY_DRAFT.bill, ...(d.bill ?? {}) }, showBill: d.showBill ?? false, compare: d.compare ?? true });
    setReady(true);
  }, []);

  const setProfile = useCallback((p: Profile) => {
    setProfileState(p);
    saveLS("polisure.profile", p);
  }, []);
  const setPolicy = useCallback((p: Policy | null) => {
    setPolicyState(p);
    setGaps(null);
    saveLS("polisure.policy", p);
  }, []);
  const setWallet = useCallback((ids: string[]) => {
    setWalletState(ids);
    saveLS("polisure.wallet", ids);
  }, []);
  const setClaim = useCallback((c: ClaimRun | null) => {
    setClaimState(c);
    saveLS("polisure.claim", c);
  }, []);

  const setDraft = useCallback((f: (d: ClaimDraft) => ClaimDraft) => {
    setDraftState((d) => {
      const n = f(d);
      saveLS("polisure.draft", { text: n.text, bill: n.bill, showBill: n.showBill, compare: n.compare });
      return n;
    });
  }, []);

  const runClaim = useCallback(
    (req: ClaimRequest) => {
      const id = ++runId.current;
      setJob({ status: "running", startedAt: Date.now(), error: null });
      api.checkClaim(req).then(
        (res: ClaimResponse) => {
          if (id !== runId.current) return; // a newer check superseded this one
          if (res.status === "needs_info") {
            setDraft((d) => {
              const answers = { ...d.answers };
              for (const q of res.questions) if (!(q.field in answers)) answers[q.field] = null;
              return { ...d, questions: res.questions, answers };
            });
            setJob({ status: "idle", startedAt: null, error: null });
          } else {
            setClaim({ request: req, response: res });
            setJob({ status: "done", startedAt: null, error: null });
          }
        },
        (e: unknown) => {
          if (id === runId.current) setJob({ status: "error", startedAt: null, error: e });
        },
      );
    },
    [setClaim, setDraft],
  );
  const ackJob = useCallback(() => setJob((j) => (j.status === "done" ? { status: "idle", startedAt: null, error: null } : j)), []);

  return (
    <Ctx.Provider
      value={{ ready, profile, setProfile, policy, setPolicy, gaps, setGaps, wallet, setWallet, claim, setClaim, draft, setDraft, job, runClaim, ackJob }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useStore() {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore outside StoreProvider");
  return s;
}
