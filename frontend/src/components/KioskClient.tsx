"use client";

import { useState } from "react";
import { CheckCircle2, CreditCard, Delete, Download, RotateCcw } from "lucide-react";
import { GermanPlateBadge } from "@/components/GermanPlateBadge";
import { Navbar } from "@/components/Navbar";
import { api, downloadInvoicePdf, PaymentSettledResult, SessionLookupResult } from "@/lib/api";
import { DICT, formatDuration, formatEur, Locale } from "@/lib/i18n";

const ROWS = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
  ["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "Ü"],
  ["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ö", "Ä"],
  ["Y", "X", "C", "V", "B", "N", "M", "-", " "],
];

export function KioskClient({ locale }: { locale: Locale }) {
  const t = DICT[locale];
  const [plate, setPlate] = useState("M-PV 2026E");
  const [lookup, setLookup] = useState<SessionLookupResult | null>(null);
  const [settled, setSettled] = useState<PaymentSettledResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function searchPlate() {
    if (!plate.trim()) return;
    setBusy(true);
    setError(null);
    setSettled(null);
    try {
      const res = await api.lookupPlate(plate);
      setLookup(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup error");
    } finally {
      setBusy(false);
    }
  }

  async function payGirocard() {
    if (!lookup?.session_id) return;
    setBusy(true);
    setError(null);
    try {
      const co = await api.createCheckout(lookup.session_id, locale, "KIOSK");
      const done = await api.confirmMockPayment(co.payment_id, "KIOSK");
      setSettled(done);
      setLookup(await api.lookupPlate(plate));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Terminal error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <Navbar locale={locale} />
      <main className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-6">
        <div className="rounded-3xl border-2 border-blue-500/30 bg-slate-900 p-6 shadow-2xl sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5">
            <div>
              <h1 className="text-2xl font-extrabold text-white">{t.kioskTitle}</h1>
              <p className="mt-1 text-sm text-slate-400">{t.kioskSubtitle}</p>
            </div>
            <button
              onClick={() => {
                setPlate("");
                setLookup(null);
                setSettled(null);
                setError(null);
              }}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-700 bg-slate-800 px-4 py-3 text-sm font-bold text-slate-200 hover:bg-slate-700"
            >
              <RotateCcw className="h-4 w-4" />
              Reset
            </button>
          </div>

          {/* Giant Plate Display */}
          <div className="mt-6 flex flex-col items-center justify-center gap-4">
            <GermanPlateBadge plate={plate || "M-AB 1234"} size="lg" />
            <div className="flex gap-3">
              <button
                onClick={searchPlate}
                disabled={busy || !plate.trim()}
                className="rounded-2xl bg-blue-600 px-8 py-4 text-lg font-extrabold text-white shadow-lg shadow-blue-900/50 transition hover:bg-blue-500 disabled:opacity-50"
              >
                {t.lookupBtn}
              </button>
              <button
                onClick={() => setPlate((p) => p.slice(0, -1))}
                className="inline-flex items-center gap-2 rounded-2xl bg-slate-800 px-5 py-4 text-base font-bold text-slate-200 hover:bg-slate-700"
              >
                <Delete className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* German QWERTZ + Umlaut Touch Keyboard */}
          <div className="mt-6 space-y-2">
            {ROWS.map((row, idx) => (
              <div key={idx} className="flex flex-wrap justify-center gap-1.5">
                {row.map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setPlate((prev) => (prev + key).slice(0, 14))}
                    className="min-w-[44px] rounded-xl border border-slate-700 bg-slate-800 px-3 py-3 font-mono text-base font-bold text-white transition active:scale-95 hover:bg-slate-700 sm:min-w-[54px] sm:py-3.5 sm:text-lg"
                  >
                    {key === " " ? "␣" : key}
                  </button>
                ))}
              </div>
            ))}
          </div>

          {error && (
            <div className="mt-6 rounded-2xl border border-rose-500/40 bg-rose-950/60 p-4 text-center text-sm text-rose-200">
              {error}
            </div>
          )}

          {lookup && !lookup.found && (
            <div className="mt-6 rounded-2xl bg-slate-950 p-5 text-center text-base font-medium text-slate-300">
              {t.notFound}
            </div>
          )}

          {lookup && lookup.found && (
            <div className="mt-6 rounded-2xl border border-slate-700 bg-slate-950 p-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-400">
                    {formatDuration(lookup.breakdown?.duration_minutes || 0, locale)} ·{" "}
                    {lookup.site_name}
                  </p>
                  <p className="mt-1 text-3xl font-extrabold text-emerald-400">
                    {formatEur(lookup.amount_due_cents, locale)}
                  </p>
                </div>

                {lookup.amount_due_cents > 0 ? (
                  <button
                    onClick={payGirocard}
                    disabled={busy}
                    className="inline-flex items-center gap-3 rounded-2xl bg-emerald-600 px-7 py-4 text-lg font-extrabold text-white shadow-lg hover:bg-emerald-500"
                  >
                    <CreditCard className="h-6 w-6" />
                    {locale === "de" ? "Girocard / NFC zahlen" : "Tap Girocard / NFC"}
                  </button>
                ) : (
                  <div className="flex items-center gap-2 rounded-2xl bg-emerald-500/15 px-5 py-3 text-base font-bold text-emerald-300">
                    <CheckCircle2 className="h-5 w-5" />
                    {settled ? t.paidBanner : t.freeStayBanner}
                  </div>
                )}
              </div>

              {(settled?.invoice_number || lookup.invoice_number) && (
                <div className="mt-4 border-t border-slate-800 pt-4">
                  <button
                    type="button"
                    onClick={() => {
                      const invNo = settled?.invoice_number || lookup.invoice_number;
                      if (invNo) downloadInvoicePdf(invNo);
                    }}
                    className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white"
                  >
                    <Download className="h-4 w-4" />
                    {t.downloadInvoice}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
