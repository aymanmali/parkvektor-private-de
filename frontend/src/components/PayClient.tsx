"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2,
  CreditCard,
  Download,
  Info,
  Search,
  Shield,
  Sparkles,
} from "lucide-react";
import { GermanPlateBadge } from "@/components/GermanPlateBadge";
import { Navbar } from "@/components/Navbar";
import {
  API_BASE_URL,
  api,
  PaymentSettledResult,
  SessionLookupResult,
  SitePublicInfo,
} from "@/lib/api";
import {
  DICT,
  formatDateTime,
  formatDuration,
  formatEur,
  Locale,
} from "@/lib/i18n";

const PAYMENT_METHODS = [
  { id: "APPLE_PAY", label: "Apple Pay / Google Pay" },
  { id: "SEPA", label: "SEPA-Lastschrift" },
  { id: "CARD", label: "Visa / Mastercard" },
  { id: "PAYPAL", label: "PayPal" },
];

export function PayClient({ locale }: { locale: Locale }) {
  const t = DICT[locale];
  const [siteInfo, setSiteInfo] = useState<SitePublicInfo | null>(null);
  const [plateInput, setPlateInput] = useState("M-PV 2026E");
  const [loading, setLoading] = useState(false);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lookup, setLookup] = useState<SessionLookupResult | null>(null);
  const [selectedMethod, setSelectedMethod] = useState("APPLE_PAY");
  const [settled, setSettled] = useState<PaymentSettledResult | null>(null);

  useEffect(() => {
    api.getSiteInfo("DE-DEMO-01").then(setSiteInfo).catch(() => null);
  }, []);

  async function handleLookup(customPlate?: string) {
    const query = (customPlate ?? plateInput).trim();
    if (!query) return;
    setLoading(true);
    setError(null);
    setSettled(null);
    try {
      const data = await api.lookupPlate(query);
      setLookup(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setLoading(false);
    }
  }

  async function handlePay() {
    if (!lookup?.session_id) return;
    setPaying(true);
    setError(null);
    try {
      const checkout = await api.createCheckout(lookup.session_id, locale, selectedMethod);
      if (checkout.requires_mock_confirm) {
        const res = await api.confirmMockPayment(checkout.payment_id, selectedMethod);
        setSettled(res);
        // Refresh session lookup to reflect PAID status
        const updated = await api.lookupPlate(plateInput);
        setLookup(updated);
      } else {
        window.location.href = checkout.checkout_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
    } finally {
      setPaying(false);
    }
  }

  const activeInvoiceNumber = settled?.invoice_number || lookup?.invoice_number;

  return (
    <div className="min-h-screen bg-[#0b1120]">
      <Navbar locale={locale} />
      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:py-12">
        <div className="grid gap-8 lg:grid-cols-12">
          {/* Left column: Plate lookup + Session checkout */}
          <div className="space-y-6 lg:col-span-7">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
                {t.payTitle}
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{t.paySubtitle}</p>
            </div>

            {/* Plate Entry Card */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                {t.plateLabel}
              </label>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleLookup();
                }}
                className="mt-3 flex flex-col gap-3 sm:flex-row"
              >
                <div className="relative flex flex-1 items-center overflow-hidden rounded-xl border-2 border-slate-700 bg-white focus-within:border-blue-500">
                  <div className="flex h-full flex-col items-center justify-center bg-[#003399] px-2.5 py-2 text-white">
                    <span className="text-[8px] text-amber-300">★★★</span>
                    <span className="text-xs font-bold">D</span>
                  </div>
                  <input
                    type="text"
                    value={plateInput}
                    onChange={(e) => setPlateInput(e.target.value.toUpperCase())}
                    placeholder={t.platePlaceholder}
                    className="w-full bg-transparent px-3 py-3 font-mono text-lg font-bold tracking-wider text-slate-950 outline-none placeholder:text-slate-400"
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-900/40 transition hover:bg-blue-500 disabled:opacity-60"
                >
                  <Search className="h-4 w-4" />
                  {t.lookupBtn}
                </button>
              </form>

              {/* Quick-fill demo plates */}
              <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <span>{t.demoQuickFill}</span>
                {["M-PV 2026E", "B-XY 420"].map((sample) => (
                  <button
                    key={sample}
                    type="button"
                    onClick={() => {
                      setPlateInput(sample);
                      handleLookup(sample);
                    }}
                    className="rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 font-mono text-slate-200 transition hover:border-blue-500 hover:text-white"
                  >
                    {sample}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className="rounded-xl border border-rose-500/40 bg-rose-950/50 p-4 text-sm text-rose-200">
                {error}
              </div>
            )}

            {/* Lookup Result Card */}
            {lookup && !lookup.found && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 text-sm text-slate-300">
                {t.notFound}
              </div>
            )}

            {lookup && lookup.found && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/90 p-6 shadow-xl">
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
                  <div>
                    <p className="text-xs font-medium text-slate-400">{lookup.site_name}</p>
                    <div className="mt-1.5">
                      <GermanPlateBadge
                        plate={lookup.plate_display || plateInput}
                        country={lookup.plate_country || "DE"}
                        size="lg"
                      />
                    </div>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider ${
                      lookup.status === "PAID" || lookup.amount_due_cents === 0
                        ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30"
                        : "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30"
                    }`}
                  >
                    {lookup.status}
                  </span>
                </div>

                {/* Timestamps & Breakdown */}
                <div className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
                  <div>
                    <p className="text-xs text-slate-400">{t.entryLabel}</p>
                    <p className="mt-0.5 font-medium text-white">
                      {formatDateTime(lookup.entry_at, locale)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">{t.exitLabel}</p>
                    <p className="mt-0.5 font-medium text-white">
                      {formatDateTime(lookup.exit_at, locale)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">{t.durationLabel}</p>
                    <p className="mt-0.5 font-medium text-white">
                      {formatDuration(lookup.breakdown?.duration_minutes || 0, locale)}
                    </p>
                  </div>
                </div>

                {lookup.breakdown && (
                  <div className="mt-5 space-y-2 rounded-xl bg-slate-950/70 p-4 text-sm">
                    <div className="flex justify-between text-slate-400">
                      <span>{t.freeApplied}</span>
                      <span>{formatDuration(lookup.breakdown.free_minutes_applied, locale)}</span>
                    </div>
                    <div className="flex justify-between text-slate-400">
                      <span>{t.billableHours}</span>
                      <span>{lookup.breakdown.billable_hours} h</span>
                    </div>
                    <div className="flex justify-between text-slate-400">
                      <span>{t.netLabel}</span>
                      <span>{formatEur(lookup.breakdown.net_cents, locale)}</span>
                    </div>
                    <div className="flex justify-between text-slate-400">
                      <span>{t.vatLabel}</span>
                      <span>{formatEur(lookup.breakdown.vat_cents, locale)}</span>
                    </div>
                    <div className="flex justify-between border-t border-slate-800 pt-2.5 text-base font-bold text-white">
                      <span>{t.totalDue}</span>
                      <span className="text-emerald-400">
                        {formatEur(lookup.amount_due_cents, locale)}
                      </span>
                    </div>
                  </div>
                )}

                {/* Free stay / Paid state / Payment controls */}
                {lookup.amount_due_cents === 0 && !activeInvoiceNumber && (
                  <div className="mt-5 flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-200">
                    <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" />
                    <span>{t.freeStayBanner}</span>
                  </div>
                )}

                {activeInvoiceNumber && (
                  <div className="mt-5 space-y-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
                    <div className="flex items-center gap-2.5 text-sm font-medium text-emerald-200">
                      <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                      <span>{t.paidBanner}</span>
                    </div>
                    <a
                      href={`${API_BASE_URL}/api/v1/public/invoices/${activeInvoiceNumber}/pdf`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500"
                    >
                      <Download className="h-4 w-4" />
                      {t.downloadInvoice} ({activeInvoiceNumber})
                    </a>
                  </div>
                )}

                {lookup.amount_due_cents > 0 && (
                  <div className="mt-6 space-y-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                      {t.payMethodLabel}
                    </p>
                    <div className="grid grid-cols-2 gap-2.5">
                      {PAYMENT_METHODS.map((pm) => (
                        <button
                          key={pm.id}
                          type="button"
                          onClick={() => setSelectedMethod(pm.id)}
                          className={`rounded-xl border px-3 py-2.5 text-left text-xs font-semibold transition ${
                            selectedMethod === pm.id
                              ? "border-blue-500 bg-blue-600/20 text-white"
                              : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700"
                          }`}
                        >
                          {pm.label}
                        </button>
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={handlePay}
                      disabled={paying}
                      className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-emerald-600 px-5 py-3.5 text-sm font-bold text-white shadow-lg transition hover:from-blue-500 hover:to-emerald-500 disabled:opacity-60"
                    >
                      <CreditCard className="h-4 w-4" />
                      {t.payNowBtn} — {formatEur(lookup.amount_due_cents, locale)}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right column: Mall Tariff Info & DSGVO Trust Card */}
          <div className="space-y-6 lg:col-span-5">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/75 p-6">
              <div className="flex items-center gap-2 text-blue-400">
                <Sparkles className="h-4 w-4" />
                <h2 className="text-sm font-semibold uppercase tracking-wider">
                  {t.tariffCardTitle}
                </h2>
              </div>
              {siteInfo ? (
                <div className="mt-4 space-y-3 text-sm">
                  <p className="font-semibold text-white">{siteInfo.name}</p>
                  <p className="text-xs text-slate-400">{siteInfo.address}</p>
                  <div className="space-y-2 border-t border-slate-800 pt-3">
                    <div className="flex justify-between">
                      <span className="text-slate-400">{t.weekdayFree}</span>
                      <span className="font-semibold text-emerald-400">
                        {Math.floor(siteInfo.weekday_free_minutes / 60)} h
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{t.weekendFree}</span>
                      <span className="font-semibold text-emerald-400">
                        {t.weekendFreeValue}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{t.driveThrough}</span>
                      <span className="font-medium text-slate-200">
                        {siteInfo.drive_through_grace_minutes} min
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{t.payLater}</span>
                      <span className="font-medium text-slate-200">
                        {siteInfo.pay_later_grace_hours} h
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-xs text-slate-400">Süd-Galerie Muster-Parkhaus (Demo)</p>
              )}
            </div>

            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-950/20 p-6">
              <div className="flex items-center gap-2 text-emerald-400">
                <Shield className="h-4 w-4" />
                <h3 className="text-xs font-semibold uppercase tracking-wider">
                  DSGVO Privacy-by-Design
                </h3>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-slate-300">{t.privacyFooter}</p>
              <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
                <Info className="h-3.5 w-3.5 text-blue-400" />
                <span>§ 14 UStG / § 147 AO GoBD Beleg ohne Kamerabilder</span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
