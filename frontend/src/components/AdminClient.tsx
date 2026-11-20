"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Download,
  Euro,
  FileText,
  Play,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Users,
} from "lucide-react";
import { GermanPlateBadge } from "@/components/GermanPlateBadge";
import { Navbar } from "@/components/Navbar";
import {
  AdminDisputeItem,
  AdminOverview,
  AdminSession,
  api,
  downloadAdminArtifact,
  DSGVOPurgeAuditRow,
  ViolationAdminItem,
} from "@/lib/api";
import {
  DICT,
  formatDateTime,
  formatDuration,
  formatEur,
  Locale,
} from "@/lib/i18n";

export function AdminClient({ locale }: { locale: Locale }) {
  const t = DICT[locale];
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [auditLog, setAuditLog] = useState<DSGVOPurgeAuditRow[]>([]);
  const [violations, setViolations] = useState<ViolationAdminItem[]>([]);
  const [disputes, setDisputes] = useState<AdminDisputeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [purging, setPurging] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  // Simulator form state
  const [simLane, setSimLane] = useState("DE-DEMO-01-IN-1");
  const [simDirection, setSimDirection] = useState<"ENTRY" | "EXIT">("ENTRY");
  const [simPlate, setSimPlate] = useState("M-EV 555E");
  const [simVendor, setSimVendor] = useState("edge_ai");
  const [simMinutesAgo, setSimMinutesAgo] = useState(0);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, sess, log, viol, disp] = await Promise.all([
        api.adminOverview(),
        api.adminSessions(),
        api.adminAuditLog(),
        api.adminViolations(),
        api.adminDisputes(),
      ]);
      setOverview(ov);
      setSessions(sess);
      setAuditLog(log);
      setViolations(viol);
      setDisputes(disp);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Failed to connect to backend");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function handleSimulate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const res = await api.adminSimulatePass({
        lane_code: simLane,
        direction: simDirection,
        plate_raw: simPlate,
        vendor: simVendor,
        minutes_ago: simMinutesAgo,
      });
      setBanner(
        `${res.plate_display} (${simDirection}) -> ${res.action} (${formatEur(res.calculated_fee_cents, locale)})`
      );
      await loadAll();
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Simulation failed");
    }
  }

  async function handleReconcile(
    session: AdminSession,
    action: "APPROVE_PAIR" | "MARK_FREE"
  ) {
    try {
      await api.adminReconcile(
        session.id,
        session.plate_display || session.fuzzy_candidate_plate || "",
        action
      );
      setBanner(`Reconciled session ${session.id.slice(0, 8)} (${action})`);
      await loadAll();
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Reconciliation failed");
    }
  }

  async function handlePurge() {
    setPurging(true);
    try {
      const res = await api.adminRunPurge(true);
      setBanner(
        `DSGVO Purge: ${res.sessions_purged} sessions anonymized, ${res.s3_objects_deleted} image objects deleted`
      );
      await loadAll();
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Purge failed");
    } finally {
      setPurging(false);
    }
  }

  async function handleEscalateOverdue() {
    const res = await api.adminEscalateOverdue();
    setBanner(`Escalated ${res.escalated_count} overdue PayLater session(s) to QA Queue`);
    await loadAll();
  }

  async function handleViolationQA(id: string, decision: "APPROVE" | "REJECT") {
    await api.adminReviewViolationQA(id, decision);
    setBanner(
      decision === "REJECT"
        ? "Violation rejected & session PII immediately purged (DSGVO)"
        : "Violation QA-approved — ready for KBA § 39 StVG lookup"
    );
    await loadAll();
  }

  async function handleKBALookup(id: string) {
    const res = await api.adminTriggerKBA(id, "mock_kba");
    setBanner(`KBA § 39 StVG resolved (${res.kba_request_ref}) -> ${res.status}`);
    await loadAll();
  }

  async function handleResolveDispute(id: string, decision: "ACCEPT_CANCEL" | "REJECT_UPHOLD") {
    await api.adminResolveDispute(id, decision);
    setBanner(`Dispute resolved (${decision})`);
    await loadAll();
  }

  async function downloadWithAdminKey(path: string, filename: string) {
    await downloadAdminArtifact(path, filename);
  }

  const reconciliationItems = sessions.filter((s) => s.status === "RECONCILIATION_NEEDED");
  const onlineLanes = overview?.lanes.filter((l) => l.online).length || 0;

  return (
    <div className="min-h-screen bg-[#0b1120]">
      <Navbar locale={locale} />
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">{t.adminTitle}</h1>
            <p className="mt-1 text-sm text-slate-400">
              {overview ? `${overview.site_name} (${overview.site_code}) · ` : ""}
              {t.adminSubtitle}
            </p>
          </div>
          <button
            onClick={loadAll}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-3.5 py-2 text-xs font-semibold text-slate-200 transition hover:border-blue-500"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {banner && (
          <div className="rounded-xl border border-blue-500/40 bg-blue-950/50 px-4 py-3 text-sm text-blue-100">
            {banner}
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>{t.kpiOccupancy}</span>
              <Users className="h-4 w-4 text-blue-400" />
            </div>
            <p className="mt-2 text-2xl font-bold text-white">
              {overview ? `${overview.active_vehicles} / ${overview.total_spaces}` : "—"}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {overview ? `${overview.occupancy_percent}%` : ""}
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>{t.kpiRevenue}</span>
              <Euro className="h-4 w-4 text-emerald-400" />
            </div>
            <p className="mt-2 text-2xl font-bold text-emerald-400">
              {overview ? formatEur(overview.total_revenue_cents, locale) : "—"}
            </p>
            <p className="mt-1 text-xs text-slate-400">incl. 19% MwSt.</p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>{t.kpiCameras}</span>
              <Camera className="h-4 w-4 text-cyan-400" />
            </div>
            <p className="mt-2 text-2xl font-bold text-white">
              {overview ? `${onlineLanes} / ${overview.lanes.length}` : "—"}
            </p>
            <p className="mt-1 text-xs text-slate-400">Edge AI + Smart Webhooks</p>
          </div>

          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-950/20 p-5">
            <div className="flex items-center justify-between text-xs text-emerald-300">
              <span>{t.kpiPurged}</span>
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
            </div>
            <p className="mt-2 text-2xl font-bold text-emerald-300">
              {overview ? overview.total_purged_sessions : "—"}
            </p>
            <p className="mt-1 text-xs text-emerald-400/80">Art. 5(1)(e) DSGVO</p>
          </div>
        </div>

        {/* Lanes + Simulator Row */}
        <div className="grid gap-6 lg:grid-cols-12">
          {/* Lanes Health */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 lg:col-span-5">
            <h2 className="text-sm font-semibold text-white">{t.lanesTitle}</h2>
            <div className="mt-4 space-y-3">
              {overview?.lanes.map((ln) => (
                <div
                  key={ln.lane_code}
                  className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 p-3.5"
                >
                  <div>
                    <p className="text-sm font-semibold text-white">{ln.name}</p>
                    <p className="font-mono text-xs text-slate-400">
                      {ln.lane_code} · {ln.capture_mode} ({ln.camera_vendor})
                    </p>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                      ln.online
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    <span
                      className={`h-2 w-2 rounded-full ${
                        ln.online ? "bg-emerald-400" : "bg-slate-500"
                      }`}
                    />
                    {ln.direction}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Live Camera Pass Simulator */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 lg:col-span-7">
            <h2 className="text-sm font-semibold text-white">{t.simulatorTitle}</h2>
            <form onSubmit={handleSimulate} className="mt-4 grid gap-3 sm:grid-cols-2">
              <div>
                <label className="text-xs text-slate-400">{t.simLane}</label>
                <select
                  value={simLane}
                  onChange={(e) => {
                    setSimLane(e.target.value);
                    setSimDirection(e.target.value.includes("-OUT-") ? "EXIT" : "ENTRY");
                  }}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                >
                  <option value="DE-DEMO-01-IN-1">DE-DEMO-01-IN-1 (Entry)</option>
                  <option value="DE-DEMO-01-OUT-1">DE-DEMO-01-OUT-1 (Exit)</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-slate-400">{t.simDirection}</label>
                <select
                  value={simDirection}
                  onChange={(e) => setSimDirection(e.target.value as "ENTRY" | "EXIT")}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                >
                  <option value="ENTRY">ENTRY</option>
                  <option value="EXIT">EXIT</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-slate-400">{t.simPlate}</label>
                <input
                  value={simPlate}
                  onChange={(e) => setSimPlate(e.target.value.toUpperCase())}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm font-bold text-white"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-slate-400">{t.simVendor}</label>
                  <select
                    value={simVendor}
                    onChange={(e) => setSimVendor(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-sm text-white"
                  >
                    <option value="edge_ai">edge_ai</option>
                    <option value="axis">axis</option>
                    <option value="hikvision">hikvision</option>
                    <option value="arh">arh</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-400">{t.simMinutesAgo}</label>
                  <input
                    type="number"
                    min={0}
                    max={4320}
                    value={simMinutesAgo}
                    onChange={(e) => setSimMinutesAgo(Number(e.target.value))}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-sm text-white"
                  />
                </div>
              </div>
              <div className="sm:col-span-2">
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-500"
                >
                  <Play className="h-4 w-4" />
                  {t.simTriggerBtn}
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Fuzzy OCR Reconciliation Queue */}
        <div className="rounded-2xl border border-amber-500/25 bg-amber-950/15 p-5">
          <div className="flex items-center gap-2 text-amber-300">
            <AlertTriangle className="h-4 w-4" />
            <h2 className="text-sm font-semibold">{t.reconcileTitle}</h2>
          </div>
          {reconciliationItems.length === 0 ? (
            <p className="mt-3 text-xs text-slate-400">{t.reconcileEmpty}</p>
          ) : (
            <div className="mt-4 space-y-3">
              {reconciliationItems.map((item) => (
                <div
                  key={item.id}
                  className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-amber-500/20 bg-slate-950/80 p-4"
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <GermanPlateBadge
                      plate={item.plate_display || "?"}
                      country={item.plate_country}
                      size="sm"
                    />
                    <span className="text-xs text-amber-300">↔ OCR Exit:</span>
                    <GermanPlateBadge
                      plate={item.fuzzy_candidate_plate || "?"}
                      country={item.plate_country}
                      size="sm"
                    />
                    <span className="text-xs text-slate-400">
                      {formatDuration(item.duration_minutes, locale)} ·{" "}
                      {formatEur(item.calculated_fee_cents, locale)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleReconcile(item, "APPROVE_PAIR")}
                      className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
                    >
                      {t.reconcileApprove}
                    </button>
                    <button
                      onClick={() => handleReconcile(item, "MARK_FREE")}
                      className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-emerald-500"
                    >
                      {t.reconcileFree}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Sessions Table */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
          <h2 className="text-sm font-semibold text-white">{t.sessionsTitle}</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-xs uppercase text-slate-400">
                  <th className="pb-2.5 pr-4">{t.colPlate}</th>
                  <th className="pb-2.5 pr-4">{t.colStatus}</th>
                  <th className="pb-2.5 pr-4">{t.colEntry}</th>
                  <th className="pb-2.5 pr-4">{t.colExit}</th>
                  <th className="pb-2.5 pr-4">{t.colDuration}</th>
                  <th className="pb-2.5 text-right">{t.colFee}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {sessions.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-800/30">
                    <td className="py-3 pr-4">
                      {s.plate_display ? (
                        <GermanPlateBadge
                          plate={s.plate_display}
                          country={s.plate_country}
                          size="sm"
                        />
                      ) : (
                        <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300 ring-1 ring-emerald-500/20">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          {t.purgedPlateLabel}
                        </span>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-200">
                        {s.status}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-xs text-slate-300">
                      {formatDateTime(s.entry_at, locale)}
                    </td>
                    <td className="py-3 pr-4 text-xs text-slate-300">
                      {formatDateTime(s.exit_at, locale)}
                    </td>
                    <td className="py-3 pr-4 text-xs text-slate-300">
                      {formatDuration(s.duration_minutes, locale)}
                    </td>
                    <td className="py-3 text-right font-mono text-xs font-semibold text-white">
                      {formatEur(s.calculated_fee_cents, locale)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Sprint 2: Violations QA Queue & KBA § 39 StVG */}
        <div className="rounded-2xl border border-rose-500/25 bg-slate-900/90 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-rose-300">
              <ShieldAlert className="h-5 w-5" />
              <h2 className="text-sm font-semibold text-white">{t.violationsTitle}</h2>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={handleEscalateOverdue}
                className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-amber-500"
              >
                {locale === "de" ? "Überfällige prüfen (>48h)" : "Sweep Overdue (>48h)"}
              </button>
              <button
                onClick={() =>
                  downloadWithAdminKey("/api/v1/admin/violations/kba-batch.csv", "kba_stvg39_batch.csv")
                }
                className="inline-flex items-center gap-1.5 rounded-lg border border-blue-500/40 bg-blue-950/50 px-3 py-1.5 text-xs font-semibold text-blue-200 hover:bg-blue-900/50"
              >
                <Download className="h-3.5 w-3.5" />
                KBA § 39 CSV
              </button>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {violations.length === 0 ? (
              <p className="text-xs text-slate-400">—</p>
            ) : (
              violations.map((v) => (
                <div
                  key={v.id}
                  className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950/80 p-4"
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-xs font-bold text-rose-300">{v.case_number}</span>
                    {v.plate_display ? (
                      <GermanPlateBadge plate={v.plate_display} country={v.plate_country} size="sm" />
                    ) : (
                      <span className="text-xs text-emerald-300">{t.purgedPlateLabel}</span>
                    )}
                    <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-200">
                      {v.status}
                    </span>
                    <span className="text-xs text-slate-400">
                      {formatEur(v.penalty_cents, locale)}
                      {v.keeper_name ? ` · Halter: ${v.keeper_name}` : ""}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {v.status === "QA_QUEUE" && (
                      <>
                        <button
                          onClick={() => handleViolationQA(v.id, "APPROVE")}
                          className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
                        >
                          QA Approve
                        </button>
                        <button
                          onClick={() => handleViolationQA(v.id, "REJECT")}
                          className="rounded-lg border border-emerald-500/40 bg-emerald-950/40 px-3 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-900/50"
                        >
                          Reject &amp; Purge
                        </button>
                      </>
                    )}
                    {v.status === "APPROVED" && (
                      <button
                        onClick={() => handleKBALookup(v.id)}
                        className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-500"
                      >
                        Run KBA § 39 StVG
                      </button>
                    )}
                    {(v.status === "NOTICE_SENT" || v.status === "DISPUTED") && (
                      <button
                        onClick={() =>
                          downloadWithAdminKey(
                            `/api/v1/admin/violations/${v.id}/notice.pdf`,
                            `${v.case_number}.pdf`
                          )
                        }
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-blue-500"
                      >
                        <FileText className="h-3.5 w-3.5" />
                        Notice PDF
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Sprint 2: Driver Disputes Queue */}
        {disputes.length > 0 && (
          <div className="rounded-2xl border border-blue-500/25 bg-slate-900/90 p-5">
            <div className="flex items-center gap-2 text-blue-300">
              <Scale className="h-5 w-5" />
              <h2 className="text-sm font-semibold text-white">{t.disputesAdminTitle}</h2>
            </div>
            <div className="mt-4 space-y-3">
              {disputes.map((d) => (
                <div
                  key={d.id}
                  className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950/80 p-4 text-xs"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-blue-300">{d.case_number}</span>
                      <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-slate-200">
                        {d.reason} · {d.status}
                      </span>
                    </div>
                    {d.nominated_driver_name && (
                      <p className="text-amber-200">
                        Fahrerbenennung: {d.nominated_driver_name} ({d.nominated_driver_address})
                      </p>
                    )}
                    {d.explanation && <p className="text-slate-400">{d.explanation}</p>}
                  </div>
                  {d.status === "OPEN" && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleResolveDispute(d.id, "ACCEPT_CANCEL")}
                        className="rounded-lg bg-emerald-600 px-3 py-1.5 font-semibold text-white hover:bg-emerald-500"
                      >
                        Accept &amp; Purge
                      </button>
                      <button
                        onClick={() => handleResolveDispute(d.id, "REJECT_UPHOLD")}
                        className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 font-semibold text-slate-200 hover:border-rose-500"
                      >
                        Uphold
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* DSGVO Audit Log & Manual Purge Trigger */}
        <div className="rounded-2xl border border-emerald-500/25 bg-slate-900/90 p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-emerald-400">
              <ShieldCheck className="h-5 w-5" />
              <h2 className="text-sm font-semibold text-white">{t.dsgvoTitle}</h2>
            </div>
            <button
              onClick={handlePurge}
              disabled={purging}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-60"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {purging ? t.purgeRunning : t.runPurgeBtn}
            </button>
          </div>

          {auditLog.length === 0 ? (
            <p className="mt-4 text-xs text-slate-400">{t.auditEmpty}</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left font-mono text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="pb-2 pr-4">Session UUID (Zero PII)</th>
                    <th className="pb-2 pr-4">Reason</th>
                    <th className="pb-2 pr-4">S3 Files Deleted</th>
                    <th className="pb-2 pr-4">Events Anonymized</th>
                    <th className="pb-2">Purged At</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {auditLog.map((row) => (
                    <tr key={row.id}>
                      <td className="py-2 pr-4 text-emerald-300">{row.session_uuid.slice(0, 18)}…</td>
                      <td className="py-2 pr-4">{row.purge_reason}</td>
                      <td className="py-2 pr-4">{row.s3_objects_deleted}</td>
                      <td className="py-2 pr-4">{row.events_anonymized}</td>
                      <td className="py-2">{formatDateTime(row.purged_at, locale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
