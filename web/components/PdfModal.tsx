"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { pdfUrl } from "@/lib/api";

type PdfState = { policyId: string; page?: number; quote?: string } | null;
const Ctx = createContext<{ open: (policyId: string, page?: number, quote?: string) => void }>({ open: () => {} });

export const usePdf = () => useContext(Ctx);

export function PdfProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<PdfState>(null);
  const open = useCallback((policyId: string, page?: number, quote?: string) => setState({ policyId, page, quote }), []);

  useEffect(() => {
    if (!state) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setState(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state]);

  const url = state ? pdfUrl(state.policyId, state.page) : "";
  return (
    <Ctx.Provider value={{ open }}>
      {children}
      {state && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Policy document"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-2 sm:p-6"
          onClick={() => setState(null)}
        >
          <div className="flex h-full w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-2">
              <div className="text-sm font-medium">Policy PDF{state.page ? ` · page ${state.page}` : ""}</div>
              <a href={url} target="_blank" rel="noreferrer" className="text-sm text-teal-700 underline">
                Open in new tab
              </a>
              <button type="button" onClick={() => setState(null)} className="btn btn-secondary ml-auto py-1">
                Close
              </button>
            </div>
            {state.quote && (
              <div className="border-b border-slate-200 bg-amber-50 px-4 py-2 text-sm text-slate-800">
                Look for: <span className="italic">“{state.quote}”</span>
              </div>
            )}
            {/* key forces a reload so #page=N is honoured when switching pages */}
            <iframe key={url} src={url} title="Policy PDF" className="w-full flex-1" />
          </div>
        </div>
      )}
    </Ctx.Provider>
  );
}
