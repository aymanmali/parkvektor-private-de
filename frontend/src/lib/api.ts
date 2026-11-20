import {
  buildDemoInvoicePdfBlob,
  buildDemoKbaCsvBlob,
  buildDemoNoticePdfBlob,
  demoApi,
  resetDemoState,
} from "@/lib/demoEngine";

export const IS_DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export const DEMO_ADMIN_API_KEY =
  process.env.NEXT_PUBLIC_ADMIN_API_KEY || "dev-admin-key-change-in-prod";

export { resetDemoState };

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadInvoicePdf(invoiceNumber: string): void {
  if (IS_DEMO_MODE) {
    triggerBlobDownload(buildDemoInvoicePdfBlob(invoiceNumber), `${invoiceNumber}.pdf`);
    return;
  }
  window.open(
    `${API_BASE_URL}/api/v1/public/invoices/${encodeURIComponent(invoiceNumber)}/pdf`,
    "_blank",
    "noopener,noreferrer"
  );
}

export async function downloadAdminArtifact(path: string, filename: string): Promise<void> {
  if (IS_DEMO_MODE) {
    if (path.includes("kba-batch.csv")) {
      triggerBlobDownload(buildDemoKbaCsvBlob(), filename);
      return;
    }
    const noticeMatch = path.match(/\/violations\/([^/]+)\/notice\.pdf/);
    if (noticeMatch) {
      triggerBlobDownload(buildDemoNoticePdfBlob(noticeMatch[1]), filename);
      return;
    }
    return;
  }
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
  });
  if (!res.ok) return;
  const blob = await res.blob();
  triggerBlobDownload(blob, filename);
}

export interface SitePublicInfo {
  site_code: string;
  name: string;
  address: string;
  privacy_notice_url: string;
  weekday_free_minutes: number;
  weekend_all_day_free: boolean;
  drive_through_grace_minutes: number;
  pay_later_grace_hours: number;
  hourly_tiers_cents: number[];
  daily_max_cents: number;
  vat_rate_percent: number;
}

export interface TariffBreakdown {
  duration_minutes: number;
  drive_through_free: boolean;
  is_whitelisted: boolean;
  free_minutes_applied: number;
  validated_minutes_applied: number;
  billable_minutes: number;
  billable_hours: number;
  gross_cents: number;
  net_cents: number;
  vat_cents: number;
  vat_rate_percent: number;
  currency: string;
  reason_code: string;
}

export interface SessionLookupResult {
  found: boolean;
  session_id?: string;
  site_code?: string;
  site_name?: string;
  plate_masked?: string;
  plate_display?: string;
  plate_country?: string;
  status?: string;
  entry_at?: string;
  exit_at?: string | null;
  pay_later_deadline_at?: string | null;
  amount_due_cents: number;
  paid_cents: number;
  currency: string;
  invoice_number?: string | null;
  breakdown?: TariffBreakdown | null;
}

export interface CheckoutResult {
  payment_id: string;
  provider: string;
  provider_ref: string;
  checkout_url: string;
  gross_cents: number;
  net_cents: number;
  vat_cents: number;
  currency: string;
  requires_mock_confirm: boolean;
}

export interface PaymentSettledResult {
  payment_id: string;
  session_id: string;
  status: string;
  invoice_number: string;
  invoice_pdf_url: string;
  gross_cents: number;
  net_cents: number;
  vat_cents: number;
  currency: string;
}

export interface LaneStatus {
  lane_code: string;
  name: string;
  direction: string;
  capture_mode: string;
  camera_vendor: string;
  last_heartbeat_at: string | null;
  online: boolean;
}

export interface AdminOverview {
  site_id: string;
  site_code: string;
  site_name: string;
  total_spaces: number;
  active_vehicles: number;
  occupancy_percent: number;
  reconciliation_needed_count: number;
  awaiting_payment_count: number;
  total_revenue_cents: number;
  total_purged_sessions: number;
  lanes: LaneStatus[];
}

export interface AdminSession {
  id: string;
  site_code: string;
  plate_display: string | null;
  plate_country: string;
  plate_type: string;
  fuzzy_candidate_plate: string | null;
  status: string;
  is_whitelisted: boolean;
  entry_at: string;
  exit_at: string | null;
  duration_minutes: number;
  calculated_fee_cents: number;
  paid_cents: number;
  pii_purged_at: string | null;
}

export interface DSGVOPurgeAuditRow {
  id: string;
  session_uuid: string;
  site_id: string;
  purge_reason: string;
  s3_objects_deleted: number;
  events_anonymized: number;
  purged_at: string;
}

export interface AutoPayAccount {
  driver_id: string;
  email: string;
  stripe_customer_id: string | null;
  consent_accepted_at: string;
  vehicles: { id: string; plate_normalized: string; is_active: boolean; created_at: string }[];
  recent_invoices: {
    invoice_number: string;
    site_name: string;
    gross_cents: number;
    issued_at: string;
    pdf_url: string;
  }[];
}

export interface MerchantValidationResult {
  validation_id: string;
  merchant_name: string;
  session_id: string;
  plate_display: string;
  bonus_minutes_applied: number;
  full_free: boolean;
  previous_fee_cents: number;
  new_fee_cents: number;
  session_status: string;
}

export interface ViolationAdminItem {
  id: string;
  case_number: string;
  session_id: string;
  site_name: string;
  plate_display: string | null;
  plate_country: string;
  entry_at: string | null;
  exit_at: string | null;
  duration_minutes: number;
  unpaid_fee_cents: number;
  penalty_cents: number;
  status: string;
  kba_provider: string | null;
  kba_request_ref: string | null;
  keeper_name: string | null;
  qa_reviewer: string | null;
  qa_reviewed_at: string | null;
  qa_notes: string | null;
  created_at: string;
}

export interface AdminDisputeItem {
  id: string;
  violation_id: string;
  case_number: string;
  plate_display: string | null;
  reason: string;
  explanation: string | null;
  nominated_driver_name: string | null;
  nominated_driver_address: string | null;
  status: string;
  created_at: string;
}

export interface PublicDisputeCase {
  violation_id: string;
  case_number: string;
  status: string;
  site_name: string;
  site_address: string;
  plate_display: string;
  plate_country: string;
  entry_at: string;
  exit_at: string | null;
  duration_minutes: number;
  unpaid_fee_cents: number;
  penalty_cents: number;
  currency: string;
  disputes: {
    id: string;
    reason: string;
    status: string;
    explanation: string | null;
    nominated_driver_name: string | null;
    created_at: string;
  }[];
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `API error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getSiteInfo: (siteCode = "DE-DEMO-01") =>
    IS_DEMO_MODE
      ? demoApi.getSiteInfo()
      : apiFetch<SitePublicInfo>(`/api/v1/public/sites/${encodeURIComponent(siteCode)}/info`),

  lookupPlate: (plate: string) =>
    IS_DEMO_MODE
      ? demoApi.lookupPlate(plate)
      : apiFetch<SessionLookupResult>(
          `/api/v1/public/sessions/lookup?plate=${encodeURIComponent(plate)}`
        ),

  createCheckout: (session_id: string, locale: "de" | "en", payment_method: string) =>
    IS_DEMO_MODE
      ? demoApi.createCheckout(session_id, locale, payment_method)
      : apiFetch<CheckoutResult>("/api/v1/public/payments/checkout", {
          method: "POST",
          body: JSON.stringify({ session_id, locale, payment_method }),
        }),

  confirmMockPayment: (payment_id: string, method: string) =>
    IS_DEMO_MODE
      ? demoApi.confirmMockPayment(payment_id, method)
      : apiFetch<PaymentSettledResult>("/api/v1/public/payments/mock-confirm", {
          method: "POST",
          body: JSON.stringify({ payment_id, method }),
        }),

  adminOverview: () =>
    IS_DEMO_MODE
      ? demoApi.adminOverview()
      : apiFetch<AdminOverview>("/api/v1/admin/overview", {
          headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
        }),

  adminSessions: () =>
    IS_DEMO_MODE
      ? demoApi.adminSessions()
      : apiFetch<AdminSession[]>("/api/v1/admin/sessions?limit=50", {
          headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
        }),

  adminReconcile: (sessionId: string, confirmed_plate: string, action: "APPROVE_PAIR" | "MARK_FREE") =>
    IS_DEMO_MODE
      ? demoApi.adminReconcile(sessionId, confirmed_plate, action)
      : apiFetch<AdminSession>(`/api/v1/admin/sessions/${sessionId}/reconcile`, {
          method: "POST",
          headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
          body: JSON.stringify({ confirmed_plate, action }),
        }),

  adminSimulatePass: (payload: {
    lane_code: string;
    direction: "ENTRY" | "EXIT";
    plate_raw: string;
    vendor: string;
    minutes_ago: number;
  }) =>
    IS_DEMO_MODE
      ? demoApi.adminSimulatePass(payload)
      : apiFetch<{ action: string; plate_display: string; calculated_fee_cents: number }>(
          "/api/v1/admin/simulate-pass",
          {
            method: "POST",
            headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
            body: JSON.stringify(payload),
          }
        ),

  adminAuditLog: () =>
    IS_DEMO_MODE
      ? demoApi.adminAuditLog()
      : apiFetch<DSGVOPurgeAuditRow[]>("/api/v1/admin/dsgvo/audit-log", {
          headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
        }),

  adminRunPurge: (force_immediate = true) =>
    IS_DEMO_MODE
      ? demoApi.adminRunPurge(force_immediate)
      : apiFetch<{ sessions_purged: number; s3_objects_deleted: number; events_anonymized: number }>(
          "/api/v1/admin/dsgvo/run-purge",
          {
            method: "POST",
            headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
            body: JSON.stringify({ force_immediate }),
          }
        ),

  // Sprint 2: AutoPay
  autopayRegister: (email: string, plate_raw: string, dsgvo_consent_accepted: boolean) =>
    IS_DEMO_MODE
      ? demoApi.autopayRegister(email, plate_raw, dsgvo_consent_accepted)
      : apiFetch<AutoPayAccount>("/api/v1/autopay/register", {
          method: "POST",
          body: JSON.stringify({ email, plate_raw, dsgvo_consent_accepted }),
        }),

  autopayAccount: (email: string) =>
    IS_DEMO_MODE
      ? demoApi.autopayAccount(email)
      : apiFetch<AutoPayAccount>(`/api/v1/autopay/account?email=${encodeURIComponent(email)}`),

  autopayUnlink: (vehicleId: string) =>
    IS_DEMO_MODE
      ? demoApi.autopayUnlink(vehicleId)
      : apiFetch<{ status: string }>(`/api/v1/autopay/vehicles/${vehicleId}`, { method: "DELETE" }),

  // Sprint 2: Merchant Validation
  merchantValidate: (
    merchantToken: string,
    payload: { plate_raw: string; bonus_minutes?: number; full_free?: boolean; voucher_code?: string }
  ) =>
    IS_DEMO_MODE
      ? demoApi.merchantValidate(merchantToken, payload)
      : apiFetch<MerchantValidationResult>("/api/v1/merchants/validate", {
          method: "POST",
          headers: { "X-Merchant-Token": merchantToken },
          body: JSON.stringify(payload),
        }),

  merchantRecent: (merchantToken: string) =>
    IS_DEMO_MODE
      ? demoApi.merchantRecent(merchantToken)
      : apiFetch<{
          merchant_name: string;
          default_bonus_minutes: number;
          validations: {
            id: string;
            plate_display: string | null;
            bonus_minutes: number;
            full_free: boolean;
            voucher_code: string | null;
            created_at: string;
          }[];
        }>("/api/v1/merchants/recent", {
          headers: { "X-Merchant-Token": merchantToken },
        }),

  // Sprint 2: Violations, QA & KBA § 39 StVG
  adminViolations: () =>
    IS_DEMO_MODE
      ? demoApi.adminViolations()
      : apiFetch<ViolationAdminItem[]>("/api/v1/admin/violations", {
          headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
        }),

  adminEscalateOverdue: () =>
    IS_DEMO_MODE
      ? demoApi.adminEscalateOverdue()
      : apiFetch<{ escalated_count: number; case_numbers: string[] }>(
          "/api/v1/admin/violations/escalate-overdue",
          { method: "POST", headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY } }
        ),

  adminReviewViolationQA: (violationId: string, decision: "APPROVE" | "REJECT", notes?: string) =>
    IS_DEMO_MODE
      ? demoApi.adminReviewViolationQA(violationId, decision, notes)
      : apiFetch<ViolationAdminItem>(`/api/v1/admin/violations/${violationId}/qa`, {
          method: "POST",
          headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
          body: JSON.stringify({ decision, reviewer: "Operator QA", notes }),
        }),

  adminTriggerKBA: (violationId: string, provider: "mock_kba" | "batch_csv_kba" = "mock_kba") =>
    IS_DEMO_MODE
      ? demoApi.adminTriggerKBA(violationId, provider)
      : apiFetch<ViolationAdminItem>(`/api/v1/admin/violations/${violationId}/kba-lookup`, {
          method: "POST",
          headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
          body: JSON.stringify({ provider }),
        }),

  // Sprint 2: Public & Admin Disputes
  publicDisputeCase: (caseNumber: string, plate: string) =>
    IS_DEMO_MODE
      ? demoApi.publicDisputeCase(caseNumber, plate)
      : apiFetch<PublicDisputeCase>(
          `/api/v1/public/disputes/case?case_number=${encodeURIComponent(caseNumber)}&plate=${encodeURIComponent(plate)}`
        ),

  publicSubmitDispute: (payload: {
    case_number: string;
    plate_raw: string;
    reason: string;
    explanation?: string;
    nominated_driver_name?: string;
    nominated_driver_address?: string;
  }) =>
    IS_DEMO_MODE
      ? demoApi.publicSubmitDispute(payload)
      : apiFetch<{ dispute_id: string; violation_status: string }>("/api/v1/public/disputes/submit", {
          method: "POST",
          body: JSON.stringify(payload),
        }),

  publicPayPenalty: (case_number: string, plate_raw: string) =>
    IS_DEMO_MODE
      ? demoApi.publicPayPenalty(case_number, plate_raw)
      : apiFetch<{ case_number: string; status: string; keeper_pii_purged: boolean }>(
          "/api/v1/public/disputes/pay",
          {
            method: "POST",
            body: JSON.stringify({ case_number, plate_raw }),
          }
        ),

  adminDisputes: () =>
    IS_DEMO_MODE
      ? demoApi.adminDisputes()
      : apiFetch<AdminDisputeItem[]>("/api/v1/admin/disputes", {
          headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
        }),

  adminResolveDispute: (disputeId: string, decision: "ACCEPT_CANCEL" | "REJECT_UPHOLD") =>
    IS_DEMO_MODE
      ? demoApi.adminResolveDispute(disputeId, decision)
      : apiFetch<{ dispute_status: string; violation_status: string }>(
          `/api/v1/admin/disputes/${disputeId}/resolve`,
          {
            method: "POST",
            headers: { "X-Admin-API-Key": DEMO_ADMIN_API_KEY },
            body: JSON.stringify({ decision }),
          }
        ),
};
