"use client";

import Link from "next/link";
import { useEffect } from "react";
import { ComparisonView } from "@/components/ComparisonView";
import { VerdictView } from "@/components/VerdictView";
import { MetaBadge } from "@/components/ui";
import { useStore } from "@/lib/store";

export default function VerdictPage() {
  const { ready, claim, policy, ackJob } = useStore();
  useEffect(() => ackJob(), [ackJob]);
  if (!ready) return null;
  if (!claim) {
    return (
      <div className="card space-y-3">
        <h1 className="h1">Verdict</h1>
        <p>No claim checked yet.</p>
        <Link href="/claim" className="btn btn-primary">
          Describe what happened
        </Link>
      </div>
    );
  }
  const { request, response } = claim;
  const singleId = request.policy_id || request.policy_ids?.[0] || null;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="h1">Verdict</h1>
          <p className="mt-1 text-sm text-slate-600">“{request.incident_text}”</p>
        </div>
        <MetaBadge meta={response.meta} />
      </div>
      {response.comparison ? (
        <ComparisonView c={response.comparison} />
      ) : (
        <VerdictView
          v={response.verdict}
          policyId={singleId}
          policyName={singleId === policy?.policy_id ? policy?.name : undefined}
        />
      )}
      <div className="flex flex-wrap gap-3">
        <Link href="/claim" className="btn btn-secondary">
          ← Check another claim
        </Link>
      </div>
    </div>
  );
}
