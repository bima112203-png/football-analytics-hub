import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";

export const metadata: Metadata = {
  title: "Football Analytics Hub",
  description: "Platform analisis statistik sepak bola & simulator kombinasi untuk edukasi.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id" className="dark">
      <body className="min-h-screen flex flex-col bg-[#090d16] text-gray-100 antialiased">
        <header className="sticky top-0 z-30 border-b border-gray-800 bg-[#090d16]/90 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-bold text-emerald-400">
              <span>⚽</span>
              <span>Football Analytics Hub</span>
            </Link>
            <nav className="flex items-center gap-4 text-sm text-gray-300">
              <Link href="/" className="hover:text-white">Dashboard</Link>
              <Link href="/simulator" className="hover:text-white">Simulator</Link>
              <Link href="/history" className="hover:text-white">Riwayat</Link>
            </nav>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
          {children}
        </main>

        <footer className="border-t border-gray-800 bg-[#070a11] py-6">
          <div className="mx-auto max-w-6xl space-y-3 px-4">
            <DisclaimerBanner />
            <p className="text-center text-xs text-gray-500">
              Football Analytics Hub · Platform Edukasi &amp; Analisis Statistik Sepak Bola
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
