import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ParkVektor DE — Schrankenloses Parken | Barrierless ANPR",
  description:
    "DSGVO-konformes schrankenloses Parkraummanagement & Online-Zahlung für Deutschland",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body className="min-h-screen bg-[#0b1120] text-slate-100 antialiased">{children}</body>
    </html>
  );
}
