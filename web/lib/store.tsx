"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ClaimRequest, ClaimResponse, GapsResponse, Policy, Profile } from "./types";

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

type Store = {
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

  useEffect(() => {
    setProfileState({ ...DEFAULT_PROFILE, ...loadLS<Partial<Profile>>("polisure.profile", {}) });
    setPolicyState(loadLS<Policy | null>("polisure.policy", null));
    setWalletState(loadLS<string[]>("polisure.wallet", []));
    setClaimState(loadLS<ClaimRun | null>("polisure.claim", null));
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

  return (
    <Ctx.Provider
      value={{ ready, profile, setProfile, policy, setPolicy, gaps, setGaps, wallet, setWallet, claim, setClaim }}
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
