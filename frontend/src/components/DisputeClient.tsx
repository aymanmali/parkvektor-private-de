"use client";

import { useState } from "react";
import { CheckCircle2, CreditCard, Scale, Search, Send } from "lucide-react";
import { GermanPlateBadge } from "@/components/GermanPlateBadge";
import { Navbar } from "@/components/Navbar";
import { api, PublicDisputeCase } from "@/lib/api";
import { DICT, formatDateTime, formatDuration, formatEur, Locale } from "@/lib/i18n";

const REASONS = [
  { id: "NOT_DRIVER", de: "Ich war nicht der Fahrer (Fahrerbenennung / BGH)", en: "I was not driving (Nominate driver)" },
  { id: "PAID_ELSEWHERE", de: "Bereits bezahlt / Zahlungsnachweis vorhanden", en: "Already paid" },
  { id: "RECEIPT_UPLOADED", de: "Kunden-/Einkaufsbeleg vorhanden", en: "Customer / retail receipt available" },
  { id: "CAMERA_ERROR", de: "Fehlerhafte Kennzeichenerkennung", en: "Camera / OCR error" },
  { id: "OTHER", de: "Sonstiger Grund", en: "Other reason" },
];

export function DisputeClient({ locale }: { locale: Locale }) {
  const t = DICT[locale];
  const [caseNumber, setCaseNumber] = useState("VF-2026-000002");
  const [plate, setPlate] = useState("F-WD 999");
  const [caseData, setCaseData] = useState<PublicDisputeCase | null>(null);
  const [reason, setReason] = useState("NOT_DRIVER");
  const [explanation, setExplanation] = useState("");
  const [driverName, setDriverName] = useState("");
  const [driverAddress, setDriverAddress] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleLookup(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMsg(null);
    try {
      const data = await api.publicDisputeCase(caseNumber, plate);
      setCaseData(data);
    } catch (err) {
      setCaseData(null);
      setError(err instanceof Error ? err.message : "Case not found");
    }
  }

  async function handleSubmitDispute(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMsg(null);
    try {
      const res = await api.publicSubmitDispute({
        case_number: caseNumber,
        plate_raw: plate,
        reason,
        explanation: explanation || undefined,
        nominated_driver_name: reason === "NOT_DRIVER" ? driverName : undefined,
        nominated_driver_address: reason === "NOT_DRIVER" ? driverAddress : undefined,
      });
      setMsg(
        locale === "de"
          ? `Widerspruch eingereicht (Status: ${res.violation_status}). Unser Team prüft Ihren Vorgang.`
          : `Dispute submitted (Status: ${res.violation_status}). Our team will review your case.`
      );
      setCaseData(await api.publicDisputeCase(caseNumber, plate));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dispute submission failed");
    }
  }

  async function handlePayPenalty() {
    setError(null);
    try {
      await api.publicPayPenalty(caseNumber, plate);
      setMsg(
        locale === "de"
          ? "Vertragsstrafe beglichen. Halterdaten und Kameradaten wurden gemäß DSGVO gelöscht."
          : "Penalty settled. Encrypted keeper PII and session images have been purged under GDPR."
      );
      setCaseData(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment failed");
    }
  }

  return (
    <div className="min-h-screen bg-[#0b1120]">
      <Navbar locale={locale} />
      <main className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-amber-500/15 px-3 py-1 text-xs font-semibold text-amber-300 ring-1 ring-amber-500/30">
            <Scale className="h-3.5 w-3.5" />
            BGB Vertragsstrafe &amp; BGH sekundäre Darlegungslast
          </div>
          <h1 className="mt-3 text-2xl font-bold text-white sm:text-3xl">{t.disputeTitle}</h1>
          <p className="mt-2 text-sm text-slate-400">{t.disputeSubtitle}</p>
        </div>

        {/* Case + Plate dual-verification lookup */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl">
          <form onSubmit={handleLookup} className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="text-xs font-semibold uppercase text-slate-400">
                {locale === "de" ? "Aktenzeichen" : "Case Number"}
              </label>
              <input
                value={caseNumber}
                onChange={(e) => setCaseNumber(e.target.value.toUpperCase())}
                required
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 font-mono text-sm text-white"
              />
            </div>
            <div>
              <label className="text-xs font-semibold uppercase text-slate-400">
                {t.plateLabel}
              </label>
              <input
                value={plate}
                onChange={(e) => setPlate(e.target.value.toUpperCase())}
                required
                className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 font-mono text-sm font-bold text-white"
              />
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
              >
                <Search className="h-4 w-4" />
                {locale === "de" ? "Vorgang öffnen" : "Open Case"}
              </button>
            </div>
          </form>
        </div>

        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-950/50 p-4 text-sm text-rose-200">
            {error}
          </div>
        )}
        {msg && (
          <div className="flex items-center gap-2.5 rounded-xl border border-emerald-500/40 bg-emerald-950/40 p-4 text-sm text-emerald-200">
            <CheckCircle2 className="h-5 w-5 text-emerald-400" />
            <span>{msg}</span>
          </div>
        )}

        {caseData && (
          <div className="grid gap-6 lg:grid-cols-12">
            {/* Case Details & Direct Payment */}
            <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/90 p-6 lg:col-span-5">
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-bold text-amber-300">
                  {caseData.case_number}
                </span>
                <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-semibold text-amber-200">
                  {caseData.status}
                </span>
              </div>
              <GermanPlateBadge plate={caseData.plate_display} country={caseData.plate_country} />
              <div className="space-y-2 border-t border-slate-800 pt-3 text-xs text-slate-300">
                <p className="font-semibold text-white">{caseData.site_name}</p>
                <p>
                  {t.entryLabel}: {formatDateTime(caseData.entry_at, locale)}
                </p>
                <p>
                  {t.exitLabel}: {formatDateTime(caseData.exit_at, locale)} (
                  {formatDuration(caseData.duration_minutes, locale)})
                </p>
                <p className="pt-2 text-lg font-bold text-white">
                  {locale === "de" ? "Vertragsstrafe:" : "Penalty:"}{" "}
                  <span className="text-amber-300">
                    {formatEur(caseData.penalty_cents, locale)}
                  </span>
                </p>
              </div>
              {caseData.status !== "PAID" && caseData.status !== "CANCELLED" && (
                <button
                  onClick={handlePayPenalty}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-bold text-white hover:bg-emerald-500"
                >
                  <CreditCard className="h-4 w-4" />
                  {locale === "de" ? "Vertragsstrafe direkt begleichen" : "Settle Penalty Now"}
                </button>
              )}
            </div>

            {/* Widerspruch Form */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/90 p-6 lg:col-span-7">
              <h2 className="text-sm font-semibold text-white">
                {locale === "de"
                  ? "Widerspruch / Fahrerbenennung einreichen"
                  : "Submit Dispute / Nominate Driver"}
              </h2>
              <form onSubmit={handleSubmitDispute} className="mt-4 space-y-4">
                <div>
                  <label className="text-xs text-slate-400">
                    {locale === "de" ? "Grund" : "Reason"}
                  </label>
                  <select
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white"
                  >
                    {REASONS.map((r) => (
                      <option key={r.id} value={r.id}>
                        {locale === "de" ? r.de : r.en}
                      </option>
                    ))}
                  </select>
                </div>

                {reason === "NOT_DRIVER" && (
                  <div className="grid gap-3 rounded-xl border border-amber-500/25 bg-amber-950/15 p-4 sm:grid-cols-2">
                    <div>
                      <label className="text-xs text-amber-200">
                        {locale === "de" ? "Name des Fahrers *" : "Actual Driver Full Name *"}
                      </label>
                      <input
                        required
                        value={driverName}
                        onChange={(e) => setDriverName(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-amber-200">
                        {locale === "de" ? "Anschrift des Fahrers *" : "Actual Driver Address *"}
                      </label>
                      <input
                        required
                        value={driverAddress}
                        onChange={(e) => setDriverAddress(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                      />
                    </div>
                  </div>
                )}

                <div>
                  <label className="text-xs text-slate-400">
                    {locale === "de" ? "Begründung / Belegreferenz" : "Explanation / Receipt Ref"}
                  </label>
                  <textarea
                    rows={3}
                    value={explanation}
                    onChange={(e) => setExplanation(e.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                  />
                </div>

                <button
                  type="submit"
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
                >
                  <Send className="h-4 w-4" />
                  {locale === "de" ? "Widerspruch absenden" : "Submit Dispute"}
                </button>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
