import type {
  AdminDisputeItem,
  AdminOverview,
  AdminSession,
  AutoPayAccount,
  CheckoutResult,
  DSGVOPurgeAuditRow,
  LaneStatus,
  MerchantValidationResult,
  PaymentSettledResult,
  PublicDisputeCase,
  SessionLookupResult,
  SitePublicInfo,
  TariffBreakdown,
  ViolationAdminItem,
} from "@/lib/api";

const STORAGE_KEY = "parkvektor_private_de_demo_v1";
const DEMO_MERCHANT_TOKEN = "demo-merchant-kinowelt-token";
const SITE_ID = "site-de-demo-01";
const SITE_CODE = "DE-DEMO-01";
const SITE_NAME = "Süd-Galerie Muster-Parkhaus (Demo)";
const SITE_ADDRESS = "Galerieplatz 1, 80000 Musterstadt";

interface DemoSessionRecord {
  id: string;
  site_code: string;
  plate_normalized: string | null;
  plate_display: string | null;
  plate_country: string;
  plate_type: string;
  fuzzy_candidate_plate: string | null;
  status: string;
  is_whitelisted: boolean;
  entry_at: string;
  exit_at: string | null;
  pay_later_deadline_at: string | null;
  duration_minutes: number;
  validated_minutes: number;
  validated_full_free: boolean;
  calculated_fee_cents: number;
  paid_cents: number;
  invoice_number: string | null;
  pii_purged_at: string | null;
}

interface DemoPaymentRecord {
  id: string;
  session_id: string;
  method: string;
  gross_cents: number;
  net_cents: number;
  vat_cents: number;
  status: "PENDING" | "SUCCEEDED";
  invoice_number: string | null;
  created_at: string;
}

interface DemoInvoiceRecord {
  invoice_number: string;
  session_id: string;
  site_name: string;
  plate_display: string;
  entry_at: string;
  exit_at: string | null;
  duration_minutes: number;
  gross_cents: number;
  net_cents: number;
  vat_cents: number;
  method: string;
  driver_email: string | null;
  issued_at: string;
}

interface DemoAutoPayDriver {
  driver_id: string;
  email: string;
  stripe_customer_id: string;
  consent_accepted_at: string;
  vehicles: { id: string; plate_normalized: string; is_active: boolean; created_at: string }[];
}

interface DemoValidationRecord {
  id: string;
  session_id: string;
  plate_display: string | null;
  bonus_minutes: number;
  full_free: boolean;
  voucher_code: string | null;
  created_at: string;
}

interface DemoViolationRecord {
  id: string;
  case_number: string;
  session_id: string;
  site_name: string;
  plate_normalized: string | null;
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

interface DemoDisputeRecord {
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

interface DemoState {
  version: number;
  invoiceSeq: number;
  violationSeq: number;
  lanes: LaneStatus[];
  sessions: DemoSessionRecord[];
  payments: DemoPaymentRecord[];
  invoices: DemoInvoiceRecord[];
  drivers: DemoAutoPayDriver[];
  validations: DemoValidationRecord[];
  violations: DemoViolationRecord[];
  disputes: DemoDisputeRecord[];
  auditLogs: DSGVOPurgeAuditRow[];
}

let memoryState: DemoState | null = null;

function uid(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`;
}

function normalizePlate(raw: string): {
  normalized: string;
  display: string;
  country: string;
  plateType: string;
} {
  const cleaned = raw.trim().toUpperCase().replace(/\s+/g, " ");
  const alnum = cleaned.replace(/[^A-Z0-9ÄÖÜ]/g, "");
  if (!alnum) {
    return { normalized: "", display: cleaned, country: "DE", plateType: "STANDARD" };
  }

  let plateType = "STANDARD";
  if (alnum.endsWith("E") && /\dE$/.test(alnum)) {
    plateType = "EV";
  } else if (alnum.endsWith("H") && /\dH$/.test(alnum)) {
    plateType = "HISTORIC";
  }

  // Format clean DE display if user typed compact string (e.g. MPV2026E -> M-PV 2026E)
  let display = cleaned;
  if (!cleaned.includes("-") && !cleaned.includes(" ")) {
    const match = alnum.match(/^([A-ZÄÖÜ]{1,3})([A-Z]{1,2})(\d{1,4}[EH]?)$/);
    if (match) {
      display = `${match[1]}-${match[2]} ${match[3]}`;
    } else {
      display = alnum;
    }
  }

  return {
    normalized: alnum,
    display,
    country: "DE",
    plateType,
  };
}

function ocrSkeleton(normalized: string): string {
  return normalized
    .replaceAll("0", "O")
    .replaceAll("1", "I")
    .replaceAll("8", "B")
    .replaceAll("5", "S");
}

function maskPlate(display: string): string {
  if (display.length <= 4) return display;
  return `${display.slice(0, 2)}•••${display.slice(-2)}`;
}

function recentWeekdayStart(now: Date): Date {
  const d = new Date(now.getTime());
  d.setUTCHours(8, 30, 0, 0);
  if (d.getTime() > now.getTime() - 6 * 3600_000) {
    d.setUTCDate(d.getUTCDate() - 1);
  }
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6) {
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return d;
}

function calculateTariff(
  entryIso: string,
  exitIso: string,
  opts?: {
    isWhitelisted?: boolean;
    validatedMinutes?: number;
    validatedFullFree?: boolean;
  }
): TariffBreakdown {
  const entry = new Date(entryIso);
  const exit = new Date(exitIso);
  const durationMinutes = Math.max(0, Math.round((exit.getTime() - entry.getTime()) / 60_000));
  const validatedMinutes = opts?.validatedMinutes ?? 0;

  if (opts?.isWhitelisted || opts?.validatedFullFree) {
    return {
      duration_minutes: durationMinutes,
      drive_through_free: false,
      is_whitelisted: Boolean(opts?.isWhitelisted),
      free_minutes_applied: durationMinutes,
      validated_minutes_applied: validatedMinutes,
      billable_minutes: 0,
      billable_hours: 0,
      gross_cents: 0,
      net_cents: 0,
      vat_cents: 0,
      vat_rate_percent: 19,
      currency: "EUR",
      reason_code: opts?.isWhitelisted ? "WHITELIST" : "TENANT_FULL_VALIDATION",
    };
  }

  if (durationMinutes <= 15) {
    return {
      duration_minutes: durationMinutes,
      drive_through_free: true,
      is_whitelisted: false,
      free_minutes_applied: durationMinutes,
      validated_minutes_applied: 0,
      billable_minutes: 0,
      billable_hours: 0,
      gross_cents: 0,
      net_cents: 0,
      vat_cents: 0,
      vat_rate_percent: 19,
      currency: "EUR",
      reason_code: "DRIVE_THROUGH_GRACE",
    };
  }

  const day = entry.getUTCDay();
  const isWeekend = day === 0 || day === 6;
  const baseFreeMinutes = isWeekend ? 1440 : 240;
  const totalFree = baseFreeMinutes + validatedMinutes;
  const billableMinutes = Math.max(0, durationMinutes - totalFree);

  if (billableMinutes === 0) {
    return {
      duration_minutes: durationMinutes,
      drive_through_free: false,
      is_whitelisted: false,
      free_minutes_applied: Math.min(durationMinutes, baseFreeMinutes),
      validated_minutes_applied: validatedMinutes,
      billable_minutes: 0,
      billable_hours: 0,
      gross_cents: 0,
      net_cents: 0,
      vat_cents: 0,
      vat_rate_percent: 19,
      currency: "EUR",
      reason_code: isWeekend ? "WEEKEND_FREE" : "WITHIN_FREE_ALLOWANCE",
    };
  }

  const billableHours = Math.ceil(billableMinutes / 60);
  const tiers = [300, 400, 500];
  let grossCents = 0;
  for (let h = 0; h < billableHours; h++) {
    grossCents += tiers[Math.min(h, tiers.length - 1)];
  }
  const days = Math.max(1, Math.ceil(durationMinutes / 1440));
  grossCents = Math.min(grossCents, days * 2500);

  const netCents = Math.round(grossCents / 1.19);
  const vatCents = grossCents - netCents;

  return {
    duration_minutes: durationMinutes,
    drive_through_free: false,
    is_whitelisted: false,
    free_minutes_applied: baseFreeMinutes,
    validated_minutes_applied: validatedMinutes,
    billable_minutes: billableMinutes,
    billable_hours: billableHours,
    gross_cents: grossCents,
    net_cents: netCents,
    vat_cents: vatCents,
    vat_rate_percent: 19,
    currency: "EUR",
    reason_code: "STANDARD_MALL_TARIFF",
  };
}

function createInitialState(): DemoState {
  const now = new Date();
  const nowIso = now.toISOString();
  const weekdayStart = recentWeekdayStart(now);
  const oldWeekday = new Date(weekdayStart.getTime() - 7 * 86400_000);
  while (oldWeekday.getUTCDay() === 0 || oldWeekday.getUTCDay() === 6) {
    oldWeekday.setUTCDate(oldWeekday.getUTCDate() - 1);
  }

  const mpvEntry = weekdayStart.toISOString();
  const mpvExit = new Date(weekdayStart.getTime() + (5 * 60 + 35) * 60_000).toISOString();
  const mpvDeadline = new Date(weekdayStart.getTime() + 54 * 3600_000).toISOString();

  const bxyEntry = new Date(now.getTime() - 75 * 60_000).toISOString();

  const goEntry = new Date(now.getTime() - 28 * 3600_000).toISOString();
  const goExit = new Date(now.getTime() - (25 * 60 + 50) * 60_000).toISOString();

  const kdoEntry = new Date(weekdayStart.getTime() + 15 * 60_000).toISOString();
  const kdoExit = new Date(weekdayStart.getTime() + (5 * 60 + 10) * 60_000).toISOString();

  const novEntry = oldWeekday.toISOString();
  const novExit = new Date(oldWeekday.getTime() + (6 * 60 + 10) * 60_000).toISOString();

  const fwdEntry = new Date(oldWeekday.getTime() + 30 * 60_000).toISOString();
  const fwdExit = new Date(oldWeekday.getTime() + (5 * 60 + 45) * 60_000).toISOString();

  return {
    version: 1,
    invoiceSeq: 1,
    violationSeq: 3,
    lanes: [
      {
        lane_code: "DE-DEMO-01-IN-1",
        name: "Einfahrt Nord (Edge AI)",
        direction: "ENTRY",
        capture_mode: "EDGE_RTSP",
        camera_vendor: "edge_ai",
        last_heartbeat_at: nowIso,
        online: true,
      },
      {
        lane_code: "DE-DEMO-01-OUT-1",
        name: "Ausfahrt Süd (Axis Smart ANPR)",
        direction: "EXIT",
        capture_mode: "SMART_WEBHOOK",
        camera_vendor: "axis",
        last_heartbeat_at: nowIso,
        online: true,
      },
    ],
    sessions: [
      {
        id: "sess-demo-bxy420",
        site_code: SITE_CODE,
        plate_normalized: "BXY420",
        plate_display: "B-XY 420",
        plate_country: "DE",
        plate_type: "STANDARD",
        fuzzy_candidate_plate: null,
        status: "ACTIVE",
        is_whitelisted: false,
        entry_at: bxyEntry,
        exit_at: null,
        pay_later_deadline_at: null,
        duration_minutes: 75,
        validated_minutes: 0,
        validated_full_free: false,
        calculated_fee_cents: 0,
        paid_cents: 0,
        invoice_number: null,
        pii_purged_at: null,
      },
      {
        id: "sess-demo-mpv2026e",
        site_code: SITE_CODE,
        plate_normalized: "MPV2026E",
        plate_display: "M-PV 2026E",
        plate_country: "DE",
        plate_type: "EV",
        fuzzy_candidate_plate: null,
        status: "AWAITING_PAYMENT",
        is_whitelisted: false,
        entry_at: mpvEntry,
        exit_at: mpvExit,
        pay_later_deadline_at: mpvDeadline,
        duration_minutes: 335,
        validated_minutes: 0,
        validated_full_free: false,
        calculated_fee_cents: 700,
        paid_cents: 0,
        invoice_number: null,
        pii_purged_at: null,
      },
      {
        id: "sess-demo-kdo881",
        site_code: SITE_CODE,
        plate_normalized: "KDO881",
        plate_display: "K-DO 881",
        plate_country: "DE",
        plate_type: "STANDARD",
        fuzzy_candidate_plate: "K-D0 881",
        status: "RECONCILIATION_NEEDED",
        is_whitelisted: false,
        entry_at: kdoEntry,
        exit_at: kdoExit,
        pay_later_deadline_at: mpvDeadline,
        duration_minutes: 295,
        validated_minutes: 0,
        validated_full_free: false,
        calculated_fee_cents: 300,
        paid_cents: 0,
        invoice_number: null,
        pii_purged_at: null,
      },
      {
        id: "sess-demo-goab901",
        site_code: SITE_CODE,
        plate_normalized: "GÖAB901",
        plate_display: "GÖ-AB 901",
        plate_country: "DE",
        plate_type: "STANDARD",
        fuzzy_candidate_plate: null,
        status: "COMPLETED_FREE",
        is_whitelisted: false,
        entry_at: goEntry,
        exit_at: goExit,
        pay_later_deadline_at: null,
        duration_minutes: 130,
        validated_minutes: 0,
        validated_full_free: false,
        calculated_fee_cents: 0,
        paid_cents: 0,
        invoice_number: null,
        pii_purged_at: null,
      },
      {
        id: "sess-demo-nov404",
        site_code: SITE_CODE,
        plate_normalized: "NOV404",
        plate_display: "N-OV 404",
        plate_country: "DE",
        plate_type: "STANDARD",
        fuzzy_candidate_plate: null,
        status: "VIOLATION_OPEN",
        is_whitelisted: false,
        entry_at: novEntry,
        exit_at: novExit,
        pay_later_deadline_at: new Date(oldWeekday.getTime() + 54 * 3600_000).toISOString(),
        duration_minutes: 370,
        validated_minutes: 0,
        validated_full_free: false,
        calculated_fee_cents: 1200,
        paid_cents: 0,
        invoice_number: null,
        pii_purged_at: null,
      },
      {
        id: "sess-demo-fwd999",
        site_code: SITE_CODE,
        plate_normalized: "FWD999",
        plate_display: "F-WD 999",
        plate_country: "DE",
        plate_type: "STANDARD",
        fuzzy_candidate_plate: null,
        status: "VIOLATION_OPEN",
        is_whitelisted: false,
        entry_at: fwdEntry,
        exit_at: fwdExit,
        pay_later_deadline_at: new Date(oldWeekday.getTime() + 54 * 3600_000).toISOString(),
        duration_minutes: 315,
        validated_minutes: 0,
        validated_full_free: false,
        calculated_fee_cents: 700,
        paid_cents: 0,
        invoice_number: null,
        pii_purged_at: null,
      },
    ],
    payments: [],
    invoices: [],
    drivers: [
      {
        driver_id: "drv-demo-001",
        email: "demo-driver@parkvektor-de.example",
        stripe_customer_id: "cus_mock_demo001",
        consent_accepted_at: new Date(now.getTime() - 5 * 86400_000).toISOString(),
        vehicles: [
          {
            id: "veh-demo-001",
            plate_normalized: "MAP100E",
            is_active: true,
            created_at: new Date(now.getTime() - 5 * 86400_000).toISOString(),
          },
        ],
      },
    ],
    validations: [],
    violations: [
      {
        id: "viol-demo-001",
        case_number: "VF-2026-000001",
        session_id: "sess-demo-nov404",
        site_name: SITE_NAME,
        plate_normalized: "NOV404",
        plate_display: "N-OV 404",
        plate_country: "DE",
        entry_at: novEntry,
        exit_at: novExit,
        duration_minutes: 370,
        unpaid_fee_cents: 1200,
        penalty_cents: 3500,
        status: "QA_PENDING",
        kba_provider: null,
        kba_request_ref: null,
        keeper_name: null,
        qa_reviewer: null,
        qa_reviewed_at: null,
        qa_notes: null,
        created_at: new Date(oldWeekday.getTime() + 55 * 3600_000).toISOString(),
      },
      {
        id: "viol-demo-002",
        case_number: "VF-2026-000002",
        session_id: "sess-demo-fwd999",
        site_name: SITE_NAME,
        plate_normalized: "FWD999",
        plate_display: "F-WD 999",
        plate_country: "DE",
        entry_at: fwdEntry,
        exit_at: fwdExit,
        duration_minutes: 315,
        unpaid_fee_cents: 700,
        penalty_cents: 3500,
        status: "NOTICE_SENT",
        kba_provider: "mock_kba",
        kba_request_ref: "KBA-MOCK-2026-0002",
        keeper_name: "Erika Mustermann (Fictional Demo)",
        qa_reviewer: "Seed QA",
        qa_reviewed_at: new Date(oldWeekday.getTime() + 56 * 3600_000).toISOString(),
        qa_notes: "Klar lesbares Kennzeichen",
        created_at: new Date(oldWeekday.getTime() + 55 * 3600_000).toISOString(),
      },
    ],
    disputes: [],
    auditLogs: [],
  };
}

function loadState(): DemoState {
  if (typeof window === "undefined") {
    if (!memoryState) memoryState = createInitialState();
    return memoryState;
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as DemoState;
      if (parsed && parsed.version === 1 && Array.isArray(parsed.sessions)) {
        memoryState = parsed;
        return parsed;
      }
    }
  } catch {
    // fallback to fresh state
  }
  const fresh = createInitialState();
  saveState(fresh);
  return fresh;
}

function saveState(state: DemoState): void {
  memoryState = state;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // ignore storage quota errors
    }
  }
}

export function resetDemoState(): void {
  const fresh = createInitialState();
  saveState(fresh);
}

function nextInvoiceNumber(state: DemoState): string {
  const num = `RE-2026-${String(state.invoiceSeq).padStart(6, "0")}`;
  state.invoiceSeq += 1;
  return num;
}

function nextCaseNumber(state: DemoState): string {
  const num = `VF-2026-${String(state.violationSeq).padStart(6, "0")}`;
  state.violationSeq += 1;
  return num;
}

function toAdminSession(s: DemoSessionRecord): AdminSession {
  const dur =
    s.exit_at === null && s.status === "ACTIVE"
      ? Math.max(0, Math.round((Date.now() - new Date(s.entry_at).getTime()) / 60_000))
      : s.duration_minutes;
  return {
    id: s.id,
    site_code: s.site_code,
    plate_display: s.plate_display,
    plate_country: s.plate_country,
    plate_type: s.plate_type,
    fuzzy_candidate_plate: s.fuzzy_candidate_plate,
    status: s.status,
    is_whitelisted: s.is_whitelisted,
    entry_at: s.entry_at,
    exit_at: s.exit_at,
    duration_minutes: dur,
    calculated_fee_cents: s.calculated_fee_cents,
    paid_cents: s.paid_cents,
    pii_purged_at: s.pii_purged_at,
  };
}

function toViolationItem(v: DemoViolationRecord): ViolationAdminItem {
  return {
    id: v.id,
    case_number: v.case_number,
    session_id: v.session_id,
    site_name: v.site_name,
    plate_display: v.plate_display,
    plate_country: v.plate_country,
    entry_at: v.entry_at,
    exit_at: v.exit_at,
    duration_minutes: v.duration_minutes,
    unpaid_fee_cents: v.unpaid_fee_cents,
    penalty_cents: v.penalty_cents,
    status: v.status,
    kba_provider: v.kba_provider,
    kba_request_ref: v.kba_request_ref,
    keeper_name: v.keeper_name,
    qa_reviewer: v.qa_reviewer,
    qa_reviewed_at: v.qa_reviewed_at,
    qa_notes: v.qa_notes,
    created_at: v.created_at,
  };
}

function toAutoPayAccount(state: DemoState, driver: DemoAutoPayDriver): AutoPayAccount {
  const invoices = state.invoices
    .filter((inv) => inv.driver_email?.toLowerCase() === driver.email.toLowerCase())
    .sort((a, b) => b.issued_at.localeCompare(a.issued_at))
    .map((inv) => ({
      invoice_number: inv.invoice_number,
      site_name: inv.site_name,
      gross_cents: inv.gross_cents,
      issued_at: inv.issued_at,
      pdf_url: `/api/v1/public/invoices/${inv.invoice_number}/pdf`,
    }));

  return {
    driver_id: driver.driver_id,
    email: driver.email,
    stripe_customer_id: driver.stripe_customer_id,
    consent_accepted_at: driver.consent_accepted_at,
    vehicles: driver.vehicles.filter((v) => v.is_active),
    recent_invoices: invoices,
  };
}

// ---------------------------------------------------------------------------
// Pure-TypeScript PDF 1.4 Generator (Zero dependencies, valid ISO-32000 PDF)
// ---------------------------------------------------------------------------

function pdfSafeAscii(text: string): string {
  return text
    .replaceAll("€", "EUR")
    .replaceAll("Ä", "Ae")
    .replaceAll("Ö", "Oe")
    .replaceAll("Ü", "Ue")
    .replaceAll("ä", "ae")
    .replaceAll("ö", "oe")
    .replaceAll("ü", "ue")
    .replaceAll("ß", "ss")
    .replaceAll("§", "Par.")
    .replaceAll("—", "-")
    .replaceAll("–", "-")
    .replaceAll("·", "|")
    .replace(/[^\x20-\x7E]/g, " ")
    .replaceAll("\\", "\\\\")
    .replaceAll("(", "\\(")
    .replaceAll(")", "\\)");
}

function buildMinimalPdfBlob(heading: string, lines: string[]): Blob {
  const cmds: string[] = [
    "BT",
    "/F2 16 Tf",
    "50 770 Td",
    `(${pdfSafeAscii(heading)}) Tj`,
    "/F1 10 Tf",
    "0 -26 Td",
  ];
  for (const line of lines) {
    cmds.push(`(${pdfSafeAscii(line)}) Tj`);
    cmds.push("0 -16 Td");
  }
  cmds.push("ET");
  const stream = cmds.join("\n");

  const objects = [
    "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
    "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
    "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\nendobj\n",
    "4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n",
    `6 0 obj\n<< /Length ${stream.length} >>\nstream\n${stream}\nendstream\nendobj\n`,
  ];

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [0];
  for (const obj of objects) {
    offsets.push(pdf.length);
    pdf += obj;
  }
  const xrefPos = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (let i = 1; i < offsets.length; i++) {
    pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`;

  return new Blob([pdf], { type: "application/pdf" });
}

function formatEurAscii(cents: number): string {
  return `${(cents / 100).toFixed(2).replace(".", ",")} EUR`;
}

export function buildDemoInvoicePdfBlob(invoiceNumber: string): Blob {
  const state = loadState();
  const inv = state.invoices.find((item) => item.invoice_number === invoiceNumber);
  const lines = inv
    ? [
        "ParkVektor Muster-Betrieb GmbH (Demo) | Musterstrasse 10, 80000 Musterstadt",
        "USt-IdNr.: DE000000000 (Synthetischer Demo-Beleg / GoBD & Par. 14 UStG)",
        "--------------------------------------------------------------------------------",
        `Rechnungsnummer:  ${inv.invoice_number}`,
        `Ausstellungsdatum: ${new Date(inv.issued_at).toLocaleString("de-DE")}`,
        `Standort:         ${inv.site_name}`,
        `Parkdauer:        ${Math.floor(inv.duration_minutes / 60)} Std. ${inv.duration_minutes % 60} Min.`,
        `Zahlungsmethode:  ${inv.method}`,
        "--------------------------------------------------------------------------------",
        `Nettobetrag:      ${formatEurAscii(inv.net_cents)}`,
        `USt. (19% MwSt.): ${formatEurAscii(inv.vat_cents)}`,
        `Gesamtbetrag:     ${formatEurAscii(inv.gross_cents)} (BEZAHLT)`,
        "--------------------------------------------------------------------------------",
        "DSGVO Hinweis (Art. 5 Abs. 1 lit. e DSGVO & Par. 147 AO):",
        "Dieser steuerliche Beleg ist streng von Kamerabildern und Kennzeichen entkoppelt.",
        "Interactive Browser Sandbox Demo - keine echte Rechnung / no real fiscal document.",
      ]
    : [
        `Rechnungsnummer: ${invoiceNumber}`,
        "Status: Bezahlt (ParkVektor Private DE Interactive Browser Sandbox)",
      ];

  return buildMinimalPdfBlob(`ParkVektor DE - Parkbeleg (${invoiceNumber})`, lines);
}

export function buildDemoNoticePdfBlob(violationId: string): Blob {
  const state = loadState();
  const v = state.violations.find((item) => item.id === violationId);
  const total = v ? v.unpaid_fee_cents + v.penalty_cents : 4200;
  const lines = v
    ? [
        "ParkVektor Muster-Betrieb GmbH (Demo) | Musterstrasse 10, 80000 Musterstadt",
        "--------------------------------------------------------------------------------",
        `Aktenzeichen:     ${v.case_number}`,
        `Standort:         ${v.site_name}`,
        `Kennzeichen:      ${v.plate_display || "GELOESCHT"} (${v.plate_country})`,
        `Halter (Demo):    ${v.keeper_name || "Ausstehend (Par. 39 StVG)"}`,
        `KBA Referenz:     ${v.kba_request_ref || "-"}`,
        `Status:           ${v.status}`,
        "--------------------------------------------------------------------------------",
        `Offene Parkgebuehr:            ${formatEurAscii(v.unpaid_fee_cents)}`,
        `Erhoehtes Parkentgelt (BGB):   ${formatEurAscii(v.penalty_cents)}`,
        `Gesamtforderung:               ${formatEurAscii(total)}`,
        "--------------------------------------------------------------------------------",
        "Widerspruch & Fahrerbenennung (BGH sekundaere Darlegungslast):",
        "Nutzen Sie das Widerspruchsportal unter /de/dispute mit Aktenzeichen & Kennzeichen.",
        "HINWEIS: Synthetischer Demo-Vorgang im Browser - keine echte Zahlungsaufforderung.",
      ]
    : ["Synthetischer Demo-Bescheid (ParkVektor Private DE)"];

  return buildMinimalPdfBlob(
    `Zahlungsaufforderung / Vertragsstrafe (${v?.case_number || violationId})`,
    lines
  );
}

export function buildDemoKbaCsvBlob(): Blob {
  const state = loadState();
  const header = "case_number,plate_display,plate_country,site_name,unpaid_fee_eur,penalty_eur,status,kba_ref";
  const rows = state.violations
    .filter((v) => v.status !== "QA_REJECTED")
    .map((v) =>
      [
        v.case_number,
        v.plate_display || "",
        v.plate_country,
        `"${v.site_name}"`,
        (v.unpaid_fee_cents / 100).toFixed(2),
        (v.penalty_cents / 100).toFixed(2),
        v.status,
        v.kba_request_ref || "",
      ].join(",")
    );
  return new Blob([[header, ...rows].join("\n")], { type: "text/csv;charset=utf-8" });
}

// ---------------------------------------------------------------------------
// Full Demo Engine API (1:1 contract with FastAPI endpoints)
// ---------------------------------------------------------------------------

export const demoApi = {
  async getSiteInfo(): Promise<SitePublicInfo> {
    return {
      site_code: SITE_CODE,
      name: SITE_NAME,
      address: SITE_ADDRESS,
      privacy_notice_url: "/de/pay#dsgvo",
      weekday_free_minutes: 240,
      weekend_all_day_free: true,
      drive_through_grace_minutes: 15,
      pay_later_grace_hours: 48,
      hourly_tiers_cents: [300, 400, 500],
      daily_max_cents: 2500,
      vat_rate_percent: 19,
    };
  },

  async lookupPlate(plate: string): Promise<SessionLookupResult> {
    const state = loadState();
    const parsed = normalizePlate(plate);
    if (!parsed.normalized) {
      return { found: false, amount_due_cents: 0, paid_cents: 0, currency: "EUR" };
    }

    const session = state.sessions.find(
      (s) =>
        s.pii_purged_at === null &&
        s.plate_normalized === parsed.normalized &&
        ["ACTIVE", "AWAITING_PAYMENT", "PAID", "COMPLETED_FREE", "RECONCILIATION_NEEDED"].includes(
          s.status
        )
    );

    if (!session) {
      return { found: false, amount_due_cents: 0, paid_cents: 0, currency: "EUR" };
    }

    const refExit = session.exit_at || new Date().toISOString();
    const breakdown = calculateTariff(session.entry_at, refExit, {
      isWhitelisted: session.is_whitelisted,
      validatedMinutes: session.validated_minutes,
      validatedFullFree: session.validated_full_free,
    });
    const due = Math.max(0, breakdown.gross_cents - session.paid_cents);

    return {
      found: true,
      session_id: session.id,
      site_code: session.site_code,
      site_name: SITE_NAME,
      plate_masked: session.plate_display ? maskPlate(session.plate_display) : undefined,
      plate_display: session.plate_display || parsed.display,
      plate_country: session.plate_country,
      status: session.status,
      entry_at: session.entry_at,
      exit_at: session.exit_at,
      pay_later_deadline_at: session.pay_later_deadline_at,
      amount_due_cents: session.status === "PAID" || session.status === "COMPLETED_FREE" ? 0 : due,
      paid_cents: session.paid_cents,
      currency: "EUR",
      invoice_number: session.invoice_number,
      breakdown,
    };
  },

  async createCheckout(
    session_id: string,
    _locale: "de" | "en",
    payment_method: string
  ): Promise<CheckoutResult> {
    const state = loadState();
    const session = state.sessions.find((s) => s.id === session_id);
    if (!session) throw new Error("Parking session not found");

    const refExit = session.exit_at || new Date().toISOString();
    const breakdown = calculateTariff(session.entry_at, refExit, {
      isWhitelisted: session.is_whitelisted,
      validatedMinutes: session.validated_minutes,
      validatedFullFree: session.validated_full_free,
    });
    const gross = Math.max(0, breakdown.gross_cents - session.paid_cents);
    if (gross <= 0) throw new Error("No balance due for this session");

    const net = Math.round(gross / 1.19);
    const vat = gross - net;
    const paymentId = uid("pay");
    state.payments.push({
      id: paymentId,
      session_id: session.id,
      method: payment_method,
      gross_cents: gross,
      net_cents: net,
      vat_cents: vat,
      status: "PENDING",
      invoice_number: null,
      created_at: new Date().toISOString(),
    });
    saveState(state);

    return {
      payment_id: paymentId,
      provider: "mock",
      provider_ref: `cs_demo_${paymentId}`,
      checkout_url: `/de/pay?mock_payment=${paymentId}`,
      gross_cents: gross,
      net_cents: net,
      vat_cents: vat,
      currency: "EUR",
      requires_mock_confirm: true,
    };
  },

  async confirmMockPayment(payment_id: string, method: string): Promise<PaymentSettledResult> {
    const state = loadState();
    const payment = state.payments.find((p) => p.id === payment_id);
    if (!payment) throw new Error("Payment intent not found");
    const session = state.sessions.find((s) => s.id === payment.session_id);
    if (!session) throw new Error("Session not found");

    const invoiceNumber = payment.invoice_number || nextInvoiceNumber(state);
    payment.status = "SUCCEEDED";
    payment.method = method || payment.method;
    payment.invoice_number = invoiceNumber;

    session.paid_cents += payment.gross_cents;
    session.calculated_fee_cents = Math.max(session.calculated_fee_cents, session.paid_cents);
    session.status = "PAID";
    session.invoice_number = invoiceNumber;

    state.invoices.push({
      invoice_number: invoiceNumber,
      session_id: session.id,
      site_name: SITE_NAME,
      plate_display: session.plate_display || "DEMO",
      entry_at: session.entry_at,
      exit_at: session.exit_at,
      duration_minutes: session.duration_minutes,
      gross_cents: payment.gross_cents,
      net_cents: payment.net_cents,
      vat_cents: payment.vat_cents,
      method: payment.method,
      driver_email: null,
      issued_at: new Date().toISOString(),
    });
    saveState(state);

    return {
      payment_id: payment.id,
      session_id: session.id,
      status: "PAID",
      invoice_number: invoiceNumber,
      invoice_pdf_url: `/api/v1/public/invoices/${invoiceNumber}/pdf`,
      gross_cents: payment.gross_cents,
      net_cents: payment.net_cents,
      vat_cents: payment.vat_cents,
      currency: "EUR",
    };
  },

  async adminOverview(): Promise<AdminOverview> {
    const state = loadState();
    const activeCount = state.sessions.filter((s) => s.status === "ACTIVE").length;
    const totalSpaces = 320;
    const totalRevenue = state.payments
      .filter((p) => p.status === "SUCCEEDED")
      .reduce((acc, p) => acc + p.gross_cents, 0);

    return {
      site_id: SITE_ID,
      site_code: SITE_CODE,
      site_name: SITE_NAME,
      total_spaces: totalSpaces,
      active_vehicles: activeCount,
      occupancy_percent: Number(((activeCount / totalSpaces) * 100).toFixed(1)),
      reconciliation_needed_count: state.sessions.filter((s) => s.status === "RECONCILIATION_NEEDED")
        .length,
      awaiting_payment_count: state.sessions.filter((s) => s.status === "AWAITING_PAYMENT").length,
      total_revenue_cents: totalRevenue,
      total_purged_sessions: state.auditLogs.length,
      lanes: state.lanes.map((l) => ({ ...l, online: true })),
    };
  },

  async adminSessions(): Promise<AdminSession[]> {
    const state = loadState();
    return [...state.sessions]
      .sort((a, b) => b.entry_at.localeCompare(a.entry_at))
      .slice(0, 50)
      .map(toAdminSession);
  },

  async adminReconcile(
    sessionId: string,
    confirmed_plate: string,
    action: "APPROVE_PAIR" | "MARK_FREE"
  ): Promise<AdminSession> {
    const state = loadState();
    const session = state.sessions.find((s) => s.id === sessionId);
    if (!session) throw new Error("Session not found");

    const parsed = normalizePlate(confirmed_plate);
    if (parsed.normalized) {
      session.plate_normalized = parsed.normalized;
      session.plate_display = parsed.display;
    }
    session.fuzzy_candidate_plate = null;

    if (action === "MARK_FREE") {
      session.calculated_fee_cents = 0;
      session.status = "COMPLETED_FREE";
    } else {
      session.status = session.calculated_fee_cents > 0 ? "AWAITING_PAYMENT" : "COMPLETED_FREE";
    }
    saveState(state);
    return toAdminSession(session);
  },

  async adminSimulatePass(payload: {
    lane_code: string;
    direction: "ENTRY" | "EXIT";
    plate_raw: string;
    vendor: string;
    minutes_ago: number;
  }): Promise<{ action: string; plate_display: string; calculated_fee_cents: number }> {
    const state = loadState();
    const parsed = normalizePlate(payload.plate_raw);
    if (!parsed.normalized) throw new Error("Invalid license plate");

    const eventTime = new Date(Date.now() - Math.max(0, payload.minutes_ago) * 60_000);
    const eventIso = eventTime.toISOString();

    const lane = state.lanes.find((l) => l.lane_code === payload.lane_code);
    if (lane) {
      lane.last_heartbeat_at = new Date().toISOString();
      lane.online = true;
    }

    if (payload.direction === "ENTRY") {
      const existing = state.sessions.find(
        (s) => s.status === "ACTIVE" && s.plate_normalized === parsed.normalized
      );
      if (existing) {
        saveState(state);
        return {
          action: "DUPLICATE_ENTRY_IGNORED",
          plate_display: existing.plate_display || parsed.display,
          calculated_fee_cents: 0,
        };
      }
      state.sessions.unshift({
        id: uid("sess"),
        site_code: SITE_CODE,
        plate_normalized: parsed.normalized,
        plate_display: parsed.display,
        plate_country: parsed.country,
        plate_type: parsed.plateType,
        fuzzy_candidate_plate: null,
        status: "ACTIVE",
        is_whitelisted: false,
        entry_at: eventIso,
        exit_at: null,
        pay_later_deadline_at: null,
        duration_minutes: 0,
        validated_minutes: 0,
        validated_full_free: false,
        calculated_fee_cents: 0,
        paid_cents: 0,
        invoice_number: null,
        pii_purged_at: null,
      });
      saveState(state);
      return {
        action: "SESSION_OPENED",
        plate_display: parsed.display,
        calculated_fee_cents: 0,
      };
    }

    // EXIT pass
    let active = state.sessions.find(
      (s) => s.status === "ACTIVE" && s.plate_normalized === parsed.normalized
    );
    let fuzzyMatch = false;
    if (!active) {
      const targetSkeleton = ocrSkeleton(parsed.normalized);
      active = state.sessions.find(
        (s) =>
          s.status === "ACTIVE" &&
          s.plate_normalized !== null &&
          ocrSkeleton(s.plate_normalized) === targetSkeleton
      );
      if (active) fuzzyMatch = true;
    }

    if (!active) {
      saveState(state);
      return {
        action: "EXIT_NO_OPEN_SESSION",
        plate_display: parsed.display,
        calculated_fee_cents: 0,
      };
    }

    active.exit_at = eventIso;
    const breakdown = calculateTariff(active.entry_at, eventIso, {
      isWhitelisted: active.is_whitelisted,
      validatedMinutes: active.validated_minutes,
      validatedFullFree: active.validated_full_free,
    });
    active.duration_minutes = breakdown.duration_minutes;
    active.calculated_fee_cents = breakdown.gross_cents;
    const due = Math.max(0, breakdown.gross_cents - active.paid_cents);

    if (fuzzyMatch) {
      active.fuzzy_candidate_plate = parsed.display;
      active.status = "RECONCILIATION_NEEDED";
      active.pay_later_deadline_at = new Date(eventTime.getTime() + 48 * 3600_000).toISOString();
      saveState(state);
      return {
        action: "SESSION_FUZZY_RECONCILIATION",
        plate_display: active.plate_display || parsed.display,
        calculated_fee_cents: due,
      };
    }

    if (due === 0) {
      active.status = active.paid_cents > 0 ? "PAID" : "COMPLETED_FREE";
      saveState(state);
      return {
        action: "SESSION_CLOSED_FREE",
        plate_display: active.plate_display || parsed.display,
        calculated_fee_cents: 0,
      };
    }

    // Check AutoPay enrollment
    const enrolledDriver = state.drivers.find((d) =>
      d.vehicles.some((v) => v.is_active && v.plate_normalized === active?.plate_normalized)
    );
    if (enrolledDriver) {
      const invoiceNumber = nextInvoiceNumber(state);
      const net = Math.round(due / 1.19);
      const vat = due - net;
      state.payments.push({
        id: uid("pay"),
        session_id: active.id,
        method: "autopay_sepa",
        gross_cents: due,
        net_cents: net,
        vat_cents: vat,
        status: "SUCCEEDED",
        invoice_number: invoiceNumber,
        created_at: new Date().toISOString(),
      });
      state.invoices.push({
        invoice_number: invoiceNumber,
        session_id: active.id,
        site_name: SITE_NAME,
        plate_display: active.plate_display || parsed.display,
        entry_at: active.entry_at,
        exit_at: active.exit_at,
        duration_minutes: active.duration_minutes,
        gross_cents: due,
        net_cents: net,
        vat_cents: vat,
        method: "AutoPay (SEPA)",
        driver_email: enrolledDriver.email,
        issued_at: new Date().toISOString(),
      });
      active.paid_cents += due;
      active.status = "PAID";
      active.invoice_number = invoiceNumber;
      saveState(state);
      return {
        action: "SESSION_AUTOPAY_CHARGED",
        plate_display: active.plate_display || parsed.display,
        calculated_fee_cents: due,
      };
    }

    active.status = "AWAITING_PAYMENT";
    active.pay_later_deadline_at = new Date(eventTime.getTime() + 48 * 3600_000).toISOString();
    saveState(state);
    return {
      action: "SESSION_AWAITING_PAYLATER",
      plate_display: active.plate_display || parsed.display,
      calculated_fee_cents: due,
    };
  },

  async adminAuditLog(): Promise<DSGVOPurgeAuditRow[]> {
    const state = loadState();
    return [...state.auditLogs].sort((a, b) => b.purged_at.localeCompare(a.purged_at));
  },

  async adminRunPurge(
    _force_immediate = true
  ): Promise<{ sessions_purged: number; s3_objects_deleted: number; events_anonymized: number }> {
    const state = loadState();
    const candidates = state.sessions.filter(
      (s) => s.pii_purged_at === null && ["COMPLETED_FREE", "PAID"].includes(s.status)
    );
    const nowIso = new Date().toISOString();
    let s3Deleted = 0;
    let eventsAnon = 0;

    for (const s of candidates) {
      const reason = s.status === "PAID" ? "PAID_RETENTION_EXPIRED" : "COMPLIANT_FREE_EXIT";
      s.plate_normalized = null;
      s.plate_display = null;
      s.fuzzy_candidate_plate = null;
      s.pii_purged_at = nowIso;
      s.status = "PURGED";
      s3Deleted += 2;
      eventsAnon += 2;
      state.auditLogs.unshift({
        id: uid("audit"),
        session_uuid: s.id,
        site_id: SITE_ID,
        purge_reason: reason,
        s3_objects_deleted: 2,
        events_anonymized: 2,
        purged_at: nowIso,
      });
    }
    saveState(state);
    return {
      sessions_purged: candidates.length,
      s3_objects_deleted: s3Deleted,
      events_anonymized: eventsAnon,
    };
  },

  async autopayRegister(
    email: string,
    plate_raw: string,
    dsgvo_consent_accepted: boolean
  ): Promise<AutoPayAccount> {
    if (!dsgvo_consent_accepted) {
      throw new Error("DSGVO Art. 6 consent is required");
    }
    const state = loadState();
    const parsed = normalizePlate(plate_raw);
    if (!parsed.normalized) throw new Error("Invalid German / EU license plate");

    const normalizedEmail = email.trim().toLowerCase();
    let driver = state.drivers.find((d) => d.email.toLowerCase() === normalizedEmail);
    if (!driver) {
      driver = {
        driver_id: uid("drv"),
        email: normalizedEmail,
        stripe_customer_id: `cus_mock_${Math.random().toString(36).slice(2, 8)}`,
        consent_accepted_at: new Date().toISOString(),
        vehicles: [],
      };
      state.drivers.push(driver);
    }

    const existing = driver.vehicles.find((v) => v.plate_normalized === parsed.normalized);
    if (existing) {
      existing.is_active = true;
    } else {
      driver.vehicles.push({
        id: uid("veh"),
        plate_normalized: parsed.normalized,
        is_active: true,
        created_at: new Date().toISOString(),
      });
    }
    saveState(state);
    return toAutoPayAccount(state, driver);
  },

  async autopayAccount(email: string): Promise<AutoPayAccount> {
    const state = loadState();
    const normalizedEmail = email.trim().toLowerCase();
    const driver = state.drivers.find((d) => d.email.toLowerCase() === normalizedEmail);
    if (!driver) throw new Error("No AutoPay account found for this email");
    return toAutoPayAccount(state, driver);
  },

  async autopayUnlink(vehicleId: string): Promise<{ status: string }> {
    const state = loadState();
    for (const d of state.drivers) {
      const v = d.vehicles.find((item) => item.id === vehicleId);
      if (v) {
        v.is_active = false;
        saveState(state);
        return { status: "unlinked" };
      }
    }
    throw new Error("Vehicle not found");
  },

  async merchantValidate(
    merchantToken: string,
    payload: { plate_raw: string; bonus_minutes?: number; full_free?: boolean; voucher_code?: string }
  ): Promise<MerchantValidationResult> {
    if (merchantToken.trim() !== DEMO_MERCHANT_TOKEN) {
      throw new Error("Invalid merchant token (demo token: demo-merchant-kinowelt-token)");
    }
    const state = loadState();
    const parsed = normalizePlate(payload.plate_raw);
    const session = state.sessions.find(
      (s) =>
        s.pii_purged_at === null &&
        s.plate_normalized === parsed.normalized &&
        ["ACTIVE", "AWAITING_PAYMENT"].includes(s.status)
    );
    if (!session) {
      throw new Error(`No active or payable session found for ${parsed.display}`);
    }

    const prevFee = session.calculated_fee_cents;
    const bonus = payload.full_free ? 0 : payload.bonus_minutes ?? 120;
    session.validated_minutes += bonus;
    if (payload.full_free) session.validated_full_free = true;

    const refExit = session.exit_at || new Date().toISOString();
    const breakdown = calculateTariff(session.entry_at, refExit, {
      isWhitelisted: session.is_whitelisted,
      validatedMinutes: session.validated_minutes,
      validatedFullFree: session.validated_full_free,
    });
    session.calculated_fee_cents = breakdown.gross_cents;
    if (session.exit_at && breakdown.gross_cents <= session.paid_cents) {
      session.status = "COMPLETED_FREE";
    }

    const valId = uid("val");
    state.validations.unshift({
      id: valId,
      session_id: session.id,
      plate_display: session.plate_display,
      bonus_minutes: bonus,
      full_free: Boolean(payload.full_free),
      voucher_code: payload.voucher_code || null,
      created_at: new Date().toISOString(),
    });
    saveState(state);

    return {
      validation_id: valId,
      merchant_name: "Kino-Welt Muster-Multiplex (Demo)",
      session_id: session.id,
      plate_display: session.plate_display || parsed.display,
      bonus_minutes_applied: bonus,
      full_free: Boolean(payload.full_free),
      previous_fee_cents: prevFee,
      new_fee_cents: breakdown.gross_cents,
      session_status: session.status,
    };
  },

  async merchantRecent(merchantToken: string) {
    if (merchantToken.trim() !== DEMO_MERCHANT_TOKEN) {
      throw new Error("Invalid merchant token");
    }
    const state = loadState();
    return {
      merchant_name: "Kino-Welt Muster-Multiplex (Demo)",
      default_bonus_minutes: 120,
      validations: state.validations.slice(0, 20).map((v) => ({
        id: v.id,
        plate_display: v.plate_display,
        bonus_minutes: v.bonus_minutes,
        full_free: v.full_free,
        voucher_code: v.voucher_code,
        created_at: v.created_at,
      })),
    };
  },

  async adminViolations(): Promise<ViolationAdminItem[]> {
    const state = loadState();
    return [...state.violations]
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map(toViolationItem);
  },

  async adminEscalateOverdue(): Promise<{ escalated_count: number; case_numbers: string[] }> {
    const state = loadState();
    const nowMs = Date.now();
    const created: string[] = [];

    for (const s of state.sessions) {
      if (
        s.status === "AWAITING_PAYMENT" &&
        s.pay_later_deadline_at &&
        new Date(s.pay_later_deadline_at).getTime() < nowMs
      ) {
        const caseNumber = nextCaseNumber(state);
        s.status = "VIOLATION_OPEN";
        state.violations.unshift({
          id: uid("viol"),
          case_number: caseNumber,
          session_id: s.id,
          site_name: SITE_NAME,
          plate_normalized: s.plate_normalized,
          plate_display: s.plate_display,
          plate_country: s.plate_country,
          entry_at: s.entry_at,
          exit_at: s.exit_at,
          duration_minutes: s.duration_minutes,
          unpaid_fee_cents: Math.max(0, s.calculated_fee_cents - s.paid_cents),
          penalty_cents: 3500,
          status: "QA_PENDING",
          kba_provider: null,
          kba_request_ref: null,
          keeper_name: null,
          qa_reviewer: null,
          qa_reviewed_at: null,
          qa_notes: null,
          created_at: new Date().toISOString(),
        });
        created.push(caseNumber);
      }
    }
    saveState(state);
    return { escalated_count: created.length, case_numbers: created };
  },

  async adminReviewViolationQA(
    violationId: string,
    decision: "APPROVE" | "REJECT",
    notes?: string
  ): Promise<ViolationAdminItem> {
    const state = loadState();
    const v = state.violations.find((item) => item.id === violationId);
    if (!v) throw new Error("Violation not found");

    const nowIso = new Date().toISOString();
    v.qa_reviewer = "Operator QA";
    v.qa_reviewed_at = nowIso;
    v.qa_notes = notes || (decision === "APPROVE" ? "Plate verified" : "OCR mismatch / rejected");

    if (decision === "APPROVE") {
      v.status = "QA_APPROVED";
    } else {
      v.status = "QA_REJECTED";
      const s = state.sessions.find((item) => item.id === v.session_id);
      if (s && !s.pii_purged_at) {
        s.plate_normalized = null;
        s.plate_display = null;
        s.pii_purged_at = nowIso;
        s.status = "PURGED";
        state.auditLogs.unshift({
          id: uid("audit"),
          session_uuid: s.id,
          site_id: SITE_ID,
          purge_reason: "QA_REJECTED_IMMEDIATE_PURGE",
          s3_objects_deleted: 2,
          events_anonymized: 2,
          purged_at: nowIso,
        });
      }
      v.plate_normalized = null;
      v.plate_display = null;
    }
    saveState(state);
    return toViolationItem(v);
  },

  async adminTriggerKBA(
    violationId: string,
    provider: "mock_kba" | "batch_csv_kba" = "mock_kba"
  ): Promise<ViolationAdminItem> {
    const state = loadState();
    const v = state.violations.find((item) => item.id === violationId);
    if (!v) throw new Error("Violation not found");

    v.kba_provider = provider;
    v.kba_request_ref = `KBA-${provider === "mock_kba" ? "MOCK" : "CSV"}-${Date.now().toString().slice(-6)}`;
    v.keeper_name = "Max Mustermann (Fictional Demo)";
    v.status = "NOTICE_SENT";
    saveState(state);
    return toViolationItem(v);
  },

  async publicDisputeCase(caseNumber: string, plate: string): Promise<PublicDisputeCase> {
    const state = loadState();
    const parsed = normalizePlate(plate);
    const v = state.violations.find(
      (item) =>
        item.case_number.toUpperCase() === caseNumber.trim().toUpperCase() &&
        item.plate_normalized === parsed.normalized
    );
    if (!v) {
      throw new Error("Vorgang nicht gefunden / Case number and plate do not match.");
    }

    const disputes = state.disputes
      .filter((d) => d.violation_id === v.id)
      .map((d) => ({
        id: d.id,
        reason: d.reason,
        status: d.status,
        explanation: d.explanation,
        nominated_driver_name: d.nominated_driver_name,
        created_at: d.created_at,
      }));

    return {
      violation_id: v.id,
      case_number: v.case_number,
      status: v.status,
      site_name: v.site_name,
      site_address: SITE_ADDRESS,
      plate_display: v.plate_display || parsed.display,
      plate_country: v.plate_country,
      entry_at: v.entry_at || v.created_at,
      exit_at: v.exit_at,
      duration_minutes: v.duration_minutes,
      unpaid_fee_cents: v.unpaid_fee_cents,
      penalty_cents: v.penalty_cents,
      currency: "EUR",
      disputes,
    };
  },

  async publicSubmitDispute(payload: {
    case_number: string;
    plate_raw: string;
    reason: string;
    explanation?: string;
    nominated_driver_name?: string;
    nominated_driver_address?: string;
  }): Promise<{ dispute_id: string; violation_status: string }> {
    const state = loadState();
    const parsed = normalizePlate(payload.plate_raw);
    const v = state.violations.find(
      (item) =>
        item.case_number.toUpperCase() === payload.case_number.trim().toUpperCase() &&
        item.plate_normalized === parsed.normalized
    );
    if (!v) throw new Error("Case not found");

    const disputeId = uid("disp");
    v.status = "DISPUTED";
    state.disputes.unshift({
      id: disputeId,
      violation_id: v.id,
      case_number: v.case_number,
      plate_display: v.plate_display,
      reason: payload.reason,
      explanation: payload.explanation || null,
      nominated_driver_name: payload.nominated_driver_name || null,
      nominated_driver_address: payload.nominated_driver_address || null,
      status: "OPEN",
      created_at: new Date().toISOString(),
    });
    saveState(state);
    return { dispute_id: disputeId, violation_status: v.status };
  },

  async publicPayPenalty(
    case_number: string,
    plate_raw: string
  ): Promise<{ case_number: string; status: string; keeper_pii_purged: boolean }> {
    const state = loadState();
    const parsed = normalizePlate(plate_raw);
    const v = state.violations.find(
      (item) =>
        item.case_number.toUpperCase() === case_number.trim().toUpperCase() &&
        item.plate_normalized === parsed.normalized
    );
    if (!v) throw new Error("Case not found");

    const nowIso = new Date().toISOString();
    v.status = "PAID";
    v.keeper_name = null;
    v.plate_normalized = null;
    v.plate_display = null;

    const s = state.sessions.find((item) => item.id === v.session_id);
    if (s) {
      s.status = "PURGED";
      s.plate_normalized = null;
      s.plate_display = null;
      s.pii_purged_at = nowIso;
      state.auditLogs.unshift({
        id: uid("audit"),
        session_uuid: s.id,
        site_id: SITE_ID,
        purge_reason: "VIOLATION_SETTLED_PII_PURGED",
        s3_objects_deleted: 2,
        events_anonymized: 2,
        purged_at: nowIso,
      });
    }
    saveState(state);
    return { case_number: v.case_number, status: "PAID", keeper_pii_purged: true };
  },

  async adminDisputes(): Promise<AdminDisputeItem[]> {
    const state = loadState();
    return [...state.disputes].sort((a, b) => b.created_at.localeCompare(a.created_at));
  },

  async adminResolveDispute(
    disputeId: string,
    decision: "ACCEPT_CANCEL" | "REJECT_UPHOLD"
  ): Promise<{ dispute_status: string; violation_status: string }> {
    const state = loadState();
    const d = state.disputes.find((item) => item.id === disputeId);
    if (!d) throw new Error("Dispute not found");
    const v = state.violations.find((item) => item.id === d.violation_id);

    if (decision === "ACCEPT_CANCEL") {
      d.status = "ACCEPTED";
      if (v) {
        v.status = "CANCELLED";
        v.keeper_name = null;
      }
    } else {
      d.status = "REJECTED";
      if (v) v.status = "NOTICE_SENT";
    }
    saveState(state);
    return {
      dispute_status: d.status,
      violation_status: v?.status || "CLOSED",
    };
  },
};
