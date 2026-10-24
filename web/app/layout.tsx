import type { Metadata } from "next";
import "./globals.css";
import { StoreProvider } from "@/lib/store";
import { Nav } from "@/components/Nav";
import { PdfProvider } from "@/components/PdfModal";

export const metadata: Metadata = {
  title: "PoliSure",
  description: "Understand your health policy and estimate what a claim will pay.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <StoreProvider>
          <PdfProvider>
            <Nav />
            <main className="mx-auto w-full max-w-5xl px-4 py-6">{children}</main>
            <footer className="mx-auto max-w-5xl px-4 pb-8 text-xs text-slate-500">
              PoliSure estimates the insurer&apos;s likely decision; it is not a legal ruling. The language model reads and
              explains; payouts are computed in code.
            </footer>
          </PdfProvider>
        </StoreProvider>
      </body>
    </html>
  );
}
