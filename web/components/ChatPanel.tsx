"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ClauseChip, ErrorBox, MetaBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { AskResponse, PolicyListItem } from "@/lib/types";

type Msg = { role: "user" | "assistant"; content: string; res?: AskResponse; policyId?: string };

const SUGGESTIONS = [
  "What is the room rent limit?",
  "Is there a waiting period for pre-existing diseases?",
  "What is not covered?",
  "Is there a co-payment?",
];

/** Floating policy Q&A. Answers come only from the policy text and are shown with verified quotes. */
export function ChatPanel() {
  const { policy } = useStore();
  const [open, setOpen] = useState(false);
  const [library, setLibrary] = useState<PolicyListItem[]>([]);
  const [policyId, setPolicyId] = useState<string>("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && library.length === 0) api.listPolicies().then(setLibrary, () => {});
  }, [open, library.length]);
  useEffect(() => {
    if (policy?.policy_id) setPolicyId(policy.policy_id);
  }, [policy?.policy_id]);
  useEffect(() => {
    if (!policyId && library.length > 0) setPolicyId(library[0].policy_id);
  }, [library, policyId]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [msgs, busy, open]);

  const current = library.find((p) => p.policy_id === policyId);
  const name = current?.name || policy?.name || "a policy";

  async function send(q: string) {
    const question = q.trim();
    if (!question || !policyId || busy) return;
    setText("");
    setError(null);
    const history = msgs.slice(-4).map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: question }]);
    setBusy(true);
    try {
      const res = await api.ask(policyId, question, history);
      setMsgs((m) => [...m, { role: "assistant", content: res.answer, res, policyId }]);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 rounded-full bg-teal-700 px-5 py-3 text-sm font-semibold text-white shadow-lg hover:bg-teal-800"
        aria-label="Open policy chat"
      >
        💬 Ask about your policy
      </button>
    );

  return (
    <section
      role="dialog"
      aria-label="Policy chat"
      className="fixed bottom-5 right-5 z-40 flex h-[34rem] max-h-[85vh] w-[26rem] max-w-[calc(100vw-2rem)] flex-col rounded-2xl border border-slate-300 bg-white shadow-2xl"
    >
      <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="font-semibold">Ask about your policy</div>
          <select
            aria-label="Policy to ask about"
            value={policyId}
            onChange={(e) => {
              setPolicyId(e.target.value);
              setMsgs([]);
            }}
            className="mt-1 w-full truncate rounded border border-slate-300 bg-white px-1 py-0.5 text-xs"
          >
            {library.length === 0 && policyId && <option value={policyId}>{name}</option>}
            {library.map((p) => (
              <option key={p.policy_id} value={p.policy_id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <button type="button" onClick={() => setOpen(false)} className="rounded p-1 text-slate-600 hover:bg-slate-100" aria-label="Close chat">
          ✕
        </button>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm">
        {msgs.length === 0 && (
          <div className="space-y-2">
            <p className="text-slate-600">
              Answers come from the policy text only, with the exact quote and page. For what a claim would pay, use{" "}
              <Link href="/claim" className="underline" onClick={() => setOpen(false)}>
                What happened
              </Link>
              .
            </p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => send(s)} className="rounded-full border border-teal-300 bg-teal-50 px-3 py-1 text-xs text-teal-900 hover:bg-teal-100">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="ml-8 rounded-xl bg-teal-700 px-3 py-2 text-white">
              {m.content}
            </div>
          ) : (
            <div key={i} className="mr-4 space-y-2 rounded-xl bg-slate-100 px-3 py-2">
              <p className="whitespace-pre-line">{m.content}</p>
              {m.res?.needs_calculation && (
                <Link href="/claim" className="btn btn-primary inline-block py-1 text-xs" onClick={() => setOpen(false)}>
                  Estimate a claim →
                </Link>
              )}
              {m.res && m.res.citations.length > 0 && (
                <ul className="space-y-1.5">
                  {m.res.citations.map((c, j) => (
                    <li key={j} className="space-y-0.5">
                      <ClauseChip policyId={m.policyId} clause={c.clause} page={c.page} quote={c.quote} />
                      <blockquote className="border-l-4 border-slate-300 pl-2 text-xs italic text-slate-600">“{c.quote}”</blockquote>
                    </li>
                  ))}
                </ul>
              )}
              {m.res && (
                <div className="flex items-center gap-2">
                  <MetaBadge meta={m.res.meta} />
                </div>
              )}
            </div>
          ),
        )}
        {busy && <div className="mr-4 animate-pulse rounded-xl bg-slate-100 px-3 py-2 text-slate-600">Reading the policy… (free-tier calls are paced)</div>}
        {!!error && <ErrorBox error={error} onRetry={() => send(msgs[msgs.length - 1]?.content || "")} />}
        <div ref={endRef} />
      </div>

      <form
        className="flex gap-2 border-t border-slate-200 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask a question about the policy…"
          aria-label="Your question"
          maxLength={500}
          className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button type="submit" className="btn btn-primary" disabled={busy || !text.trim() || !policyId}>
          Ask
        </button>
      </form>
      <p className="px-4 pb-2 text-[11px] text-slate-500">Not legal or financial advice. Based only on the document you chose.</p>
    </section>
  );
}
