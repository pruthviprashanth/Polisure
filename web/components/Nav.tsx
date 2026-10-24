"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useStore } from "@/lib/store";

const LINKS = [
  { href: "/", label: "1. My policy" },
  { href: "/claim", label: "2. What happened" },
  { href: "/verdict", label: "3. Verdict" },
  { href: "/wallet", label: "My policies" },
  { href: "/recommend", label: "Find a policy" },
  { href: "/eval", label: "Eval" },
];

export function Nav() {
  const path = usePathname();
  const { job } = useStore();
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <Link href="/" className="text-lg font-bold text-teal-800">
          PoliSure
        </Link>
        <nav className="flex flex-wrap gap-1 text-sm" aria-label="Main">
          {LINKS.map((l) => {
            const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 ${active ? "bg-teal-700 text-white" : "text-slate-700 hover:bg-slate-100"}`}
              >
                {l.label}
                {l.href === "/verdict" && job.status === "running" && (
                  <span className="ml-1.5 inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent align-[-1px]" title="Checking your claim…" />
                )}
                {l.href === "/verdict" && job.status === "done" && path !== "/verdict" && (
                  <span className="ml-1.5 rounded-full bg-emerald-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">ready</span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
