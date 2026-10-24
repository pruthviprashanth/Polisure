"use client";

import { useEffect, useState } from "react";
import type { Profile } from "@/lib/types";

export function NumberField({
  id,
  label,
  value,
  onChange,
  hint,
  min = 0,
  prefix,
  placeholder,
}: {
  id: string;
  label: string;
  value: number | null;
  onChange: (n: number | null) => void;
  hint?: string;
  min?: number;
  prefix?: string;
  placeholder?: string;
}) {
  // Local string state so the user can clear the box while typing.
  const [text, setText] = useState(value === null ? "" : String(value));
  useEffect(() => {
    setText((t) => (Number(t.replace(/,/g, "")) === value && t !== "" ? t : value === null ? "" : String(value)));
  }, [value]);
  return (
    <div>
      <label htmlFor={id} className="label">
        {label}
      </label>
      <div
        className={
          prefix
            ? "flex items-center rounded-lg border border-slate-300 bg-white focus-within:border-teal-600 focus-within:ring-2 focus-within:ring-teal-600/30"
            : undefined
        }
      >
        {prefix && (
          <span aria-hidden="true" className="select-none pl-3 pr-1 text-sm font-medium text-slate-500">
            {prefix}
          </span>
        )}
        <input
          id={id}
          inputMode="numeric"
          className={prefix ? "w-full min-w-0 rounded-lg bg-transparent py-2 pr-3 pl-1 text-sm tabular-nums focus:outline-none" : "input tabular-nums"}
          value={text}
          placeholder={placeholder}
          onChange={(e) => {
            const raw = e.target.value.replace(/[^\d]/g, "");
            setText(raw);
            onChange(raw === "" ? null : Math.max(min, parseInt(raw, 10)));
          }}
        />
      </div>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function PedSelect({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: boolean | null;
  onChange: (v: boolean | null) => void;
}) {
  const opts: { v: boolean | null; l: string }[] = [
    { v: true, l: "Yes" },
    { v: false, l: "No" },
    { v: null, l: "Don't know" },
  ];
  return (
    <fieldset>
      <legend className="label">{label}</legend>
      <div className="flex gap-1" role="radiogroup" id={id}>
        {opts.map((o) => (
          <button
            key={o.l}
            type="button"
            role="radio"
            aria-checked={value === o.v}
            onClick={() => onChange(o.v)}
            className={`flex-1 rounded-lg border px-2 py-2 text-sm ${
              value === o.v ? "border-teal-700 bg-teal-700 text-white" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50"
            }`}
          >
            {o.l}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export function planForAge(age: number): string {
  if (age >= 18 && age <= 35) return "Platinum";
  if (age >= 36 && age <= 60) return "Gold";
  if (age >= 61 && age <= 65) return "Senior Citizen";
  return "outside plan bands";
}

export function ProfileForm({
  profile,
  onChange,
  hidePolicyAge = false,
}: {
  profile: Profile;
  onChange: (p: Profile) => void;
  hidePolicyAge?: boolean;
}) {
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => onChange({ ...profile, [k]: v });
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <NumberField
        id="age"
        label="Age of the insured"
        value={profile.insured_age}
        onChange={(n) => set("insured_age", n ?? 0)}
        hint={`United India plan: ${planForAge(profile.insured_age)}`}
      />
      <NumberField
        id="si"
        label="Sum insured"
        prefix="₹"
        value={profile.sum_insured}
        onChange={(n) => set("sum_insured", n ?? 0)}
        hint={`₹${profile.sum_insured.toLocaleString("en-IN")}`}
      />
      <NumberField
        id="rent"
        label="Preferred room rent per day"
        prefix="₹"
        value={profile.preferred_room_rent_per_day}
        onChange={(n) => set("preferred_room_rent_per_day", n ?? 0)}
      />
      {!hidePolicyAge && (
        <NumberField
          id="pam"
          label="Policy age (months of continuous cover)"
          value={profile.policy_age_months}
          onChange={(n) => set("policy_age_months", n ?? 0)}
        />
      )}
      <PedSelect id="ped" label="Any pre-existing conditions?" value={profile.ped} onChange={(v) => set("ped", v)} />
    </div>
  );
}
