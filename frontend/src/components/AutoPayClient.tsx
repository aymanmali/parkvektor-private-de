"use client";

import { useState } from "react";
import { CheckCircle2, Download, Trash2, Zap } from "lucide-react";
import { GermanPlateBadge } from "@/components/GermanPlateBadge";
import { Navbar } from "@/components/Navbar";
import { API_BASE_URL, api, AutoPayAccount } from "@/lib/api";
import { DICT, formatDateTime, formatEur, Locale } from "@/lib/i18n";

export function AutoPayClient({ locale }: { locale: Locale }) {
  const t = DICT[locale];
  const [email, setEmail] = useState("demo-driver@parkvektor-de.example");
  const [plate, setPlate] = useState("M-AP 2026E");
  const [consent, setConsent] = useState(true);
  const [account, setAccount] = useState<AutoPayAccount | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMsg(null);
    try {
      const data = await api.autopayRegister(email, plate, consent);
      setAccount(data);
      setMsg(
        locale === "de"
          ? "AutoPay aktiviert! Bei Ausfahrt wird automatisch abgerechnet."
          : "AutoPay activated! Eligible stays will bill automatically on exit."
      );
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadAccount() {
    setLoading(true);
    setMsg(null);
    try {
      const data = await api.autopayAccount(email);
      setAccount(data);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Account not found");
    } finally {
      setLoading(false);
    }
  }

  async function handleUnlink(vehicleId: string) {
    await api.autopayUnlink(vehicleId);
    await handleLoadAccount();
  }

  return (
    <div className="min-h-screen bg-[#0b1120]">
      <Navbar locale={locale} />
      <main className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-blue-500/15 px-3 py-1 text-xs font-semibold text-blue-300 ring-1 ring-blue-500/30">
            <Zap className="h-3.5 w-3.5" />
            {locale === "de" ? "Schrankenloses Drive-Out AutoPay" : "Frictionless Drive-Out AutoPay"}
          </div>
          <h1 className="mt-3 text-2xl font-bold text-white sm:text-3xl">{t.autopayTitle}</h1>
          <p className="mt-2 text-sm text-slate-400">{t.autopaySubtitle}</p>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl">
          <form onSubmit={handleRegister} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-xs font-semibold uppercase text-slate-400">E-Mail</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white"
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase text-slate-400">
                  {t.plateLabel}
                </label>
                <input
                  type="text"
                  required
                  value={plate}
                  onChange={(e) => setPlate(e.target.value.toUpperCase())}
                  className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 font-mono text-sm font-bold text-white"
                />
              </div>
            </div>

            <label className="flex items-start gap-3 rounded-xl border border-emerald-500/20 bg-emerald-950/20 p-3.5 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded accent-emerald-500"
              />
              <span>{t.autopayConsent}</span>
            </label>

            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:from-blue-500 hover:to-emerald-500"
              >
                <Zap className="h-4 w-4" />
                {t.autopayRegisterBtn}
              </button>
              <button
                type="button"
                onClick={handleLoadAccount}
                className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm font-medium text-slate-200 hover:border-blue-500"
              >
                {locale === "de" ? "Mein Konto laden" : "Load Existing Account"}
              </button>
            </div>
          </form>

          {msg && (
            <div className="mt-4 flex items-center gap-2 rounded-xl border border-blue-500/30 bg-blue-950/40 p-3.5 text-sm text-blue-100">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <span>{msg}</span>
            </div>
          )}
        </div>

        {account && (
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
              <h2 className="text-sm font-semibold text-white">
                {locale === "de" ? "Aktive AutoPay-Fahrzeuge" : "Enrolled AutoPay Vehicles"}
              </h2>
              <p className="mt-1 text-xs text-slate-400">{account.email}</p>
              <div className="mt-4 space-y-2.5">
                {account.vehicles.map((v) => (
                  <div
                    key={v.id}
                    className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 p-3"
                  >
                    <GermanPlateBadge plate={v.plate_normalized} size="sm" />
                    <button
                      onClick={() => handleUnlink(v.id)}
                      className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-950/60 hover:text-rose-300"
                      title="Remove plate"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
              <h2 className="text-sm font-semibold text-white">
                {locale === "de" ? "Automatische Belege (PDF)" : "Automatic VAT Invoices"}
              </h2>
              {account.recent_invoices.length === 0 ? (
                <p className="mt-4 text-xs text-slate-400">
                  {locale === "de"
                    ? "Noch keine automatischen Abrechnungen."
                    : "No automatic charges yet."}
                </p>
              ) : (
                <div className="mt-4 space-y-2.5">
                  {account.recent_invoices.map((inv) => (
                    <div
                      key={inv.invoice_number}
                      className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-xs"
                    >
                      <div>
                        <p className="font-semibold text-white">{inv.invoice_number}</p>
                        <p className="text-slate-400">
                          {formatEur(inv.gross_cents, locale)} ·{" "}
                          {formatDateTime(inv.issued_at, locale)}
                        </p>
                      </div>
                      <a
                        href={`${API_BASE_URL}${inv.pdf_url}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 rounded-lg bg-emerald-600/20 px-2.5 py-1.5 font-semibold text-emerald-300 hover:bg-emerald-600/30"
                      >
                        <Download className="h-3.5 w-3.5" />
                        PDF
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
