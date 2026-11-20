"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Film, Sparkles, Ticket } from "lucide-react";
import { GermanPlateBadge } from "@/components/GermanPlateBadge";
import { Navbar } from "@/components/Navbar";
import { api, MerchantValidationResult } from "@/lib/api";
import { DICT, formatDateTime, formatEur, Locale } from "@/lib/i18n";

export function ValidateClient({ locale }: { locale: Locale }) {
  const t = DICT[locale];
  const [token, setToken] = useState("demo-merchant-kinowelt-token");
  const [plate, setPlate] = useState("M-PV 2026E");
  const [voucher, setVoucher] = useState("CINE-2026-881");
  const [bonusMinutes, setBonusMinutes] = useState(120);
  const [fullFree, setFullFree] = useState(false);
  const [merchantName, setMerchantName] = useState("Kino-Welt Muster-Multiplex (Demo)");
  const [recent, setRecent] = useState<
    {
      id: string;
      plate_display: string | null;
      bonus_minutes: number;
      full_free: boolean;
      voucher_code: string | null;
      created_at: string;
    }[]
  >([]);
  const [result, setResult] = useState<MerchantValidationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadRecent = useCallback(async () => {
    try {
      const data = await api.merchantRecent(token);
      setMerchantName(data.merchant_name);
      setRecent(data.validations);
    } catch {
      // ignore until valid token
    }
  }, [token]);

  useEffect(() => {
    loadRecent();
  }, [loadRecent]);

  async function handleValidate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    try {
      const res = await api.merchantValidate(token, {
        plate_raw: plate,
        bonus_minutes: fullFree ? 0 : bonusMinutes,
        full_free: fullFree,
        voucher_code: voucher || undefined,
      });
      setResult(res);
      await loadRecent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    }
  }

  return (
    <div className="min-h-screen bg-[#0b1120]">
      <Navbar locale={locale} />
      <main className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full bg-purple-500/15 px-3 py-1 text-xs font-semibold text-purple-300 ring-1 ring-purple-500/30">
            <Film className="h-3.5 w-3.5" />
            {merchantName}
          </div>
          <h1 className="mt-3 text-2xl font-bold text-white sm:text-3xl">{t.validateTitle}</h1>
          <p className="mt-2 text-sm text-slate-400">{t.validateSubtitle}</p>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl">
          <form onSubmit={handleValidate} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-xs font-semibold uppercase text-slate-400">
                  {t.plateLabel}
                </label>
                <input
                  value={plate}
                  onChange={(e) => setPlate(e.target.value.toUpperCase())}
                  required
                  className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 font-mono text-base font-bold text-white"
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase text-slate-400">
                  {locale === "de" ? "Beleg-/Ticketnummer" : "Receipt / Ticket Code"}
                </label>
                <input
                  value={voucher}
                  onChange={(e) => setVoucher(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-white"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {[60, 120, 180].map((mins) => (
                <button
                  key={mins}
                  type="button"
                  onClick={() => {
                    setFullFree(false);
                    setBonusMinutes(mins);
                  }}
                  className={`rounded-xl border px-4 py-2 text-xs font-bold transition ${
                    !fullFree && bonusMinutes === mins
                      ? "border-blue-500 bg-blue-600/20 text-white"
                      : "border-slate-700 bg-slate-950 text-slate-300"
                  }`}
                >
                  +{mins / 60}h {locale === "de" ? "Freiparken" : "Free Bonus"}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setFullFree(true)}
                className={`inline-flex items-center gap-1.5 rounded-xl border px-4 py-2 text-xs font-bold transition ${
                  fullFree
                    ? "border-emerald-500 bg-emerald-600/20 text-emerald-200"
                    : "border-slate-700 bg-slate-950 text-slate-300"
                }`}
              >
                <Sparkles className="h-3.5 w-3.5" />
                100% VIP Free
              </button>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <input
                value={token}
                onChange={(e) => setToken(e.target.value)}
                className="w-64 rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5 font-mono text-xs text-slate-400"
                title="Merchant API Token"
              />
              <button
                type="submit"
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
              >
                <Ticket className="h-4 w-4" />
                {locale === "de" ? "Validierung gutschreiben" : "Apply Validation"}
              </button>
            </div>
          </form>

          {error && (
            <div className="mt-4 rounded-xl border border-rose-500/30 bg-rose-950/50 p-3.5 text-sm text-rose-200">
              {error}
            </div>
          )}

          {result && (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-200">
              <div className="flex items-center gap-2.5">
                <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                <span>
                  <strong>{result.plate_display}</strong>:{" "}
                  {formatEur(result.previous_fee_cents, locale)} →{" "}
                  <strong>{formatEur(result.new_fee_cents, locale)}</strong> ({result.session_status})
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
          <h2 className="text-sm font-semibold text-white">
            {locale === "de" ? "Letzte Mieter-Validierungen" : "Recent Tenant Validations"}
          </h2>
          <div className="mt-4 space-y-2.5">
            {recent.length === 0 ? (
              <p className="text-xs text-slate-400">—</p>
            ) : (
              recent.map((r) => (
                <div
                  key={r.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-xs"
                >
                  <div className="flex items-center gap-3">
                    {r.plate_display && <GermanPlateBadge plate={r.plate_display} size="sm" />}
                    <span className="font-semibold text-emerald-300">
                      {r.full_free ? "100% VIP FREE" : `+${r.bonus_minutes} min`}
                    </span>
                    {r.voucher_code && (
                      <span className="font-mono text-slate-400">#{r.voucher_code}</span>
                    )}
                  </div>
                  <span className="text-slate-400">{formatDateTime(r.created_at, locale)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
