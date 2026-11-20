export type Locale = "de" | "en";

export function normalizeLocale(raw: string): Locale {
  return raw === "en" ? "en" : "de";
}

export function formatEur(cents: number, locale: Locale): string {
  const euros = cents / 100;
  return new Intl.NumberFormat(locale === "de" ? "de-DE" : "en-IE", {
    style: "currency",
    currency: "EUR",
  }).format(euros);
}

export function formatDateTime(iso: string | null | undefined, locale: Locale): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Europe/Berlin",
  }).format(new Date(iso));
}

export function formatDuration(minutes: number, locale: Locale): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (locale === "de") return `${h} Std. ${m} Min.`;
  return `${h}h ${m}m`;
}

export const DICT = {
  de: {
    brandSubtitle: "Schrankenloses Parken · DSGVO-Konform",
    navPay: "Bezahlen",
    navAutoPay: "AutoPay",
    navKiosk: "Kiosk",
    navValidate: "Mieter-Rabatt",
    navDispute: "Widerspruch",
    navAdmin: "Betreiber",
    payTitle: "Schrankenloses Parken — Schnellzahlung",
    paySubtitle:
      "Geben Sie Ihr Kennzeichen ein, um Ihren aktuellen Parkvorgang einzusehen oder innerhalb der 48-Stunden-Kulanzfrist bequem online zu begleichen.",
    plateLabel: "Amtliches Kennzeichen (DE / EU)",
    platePlaceholder: "z. B. M-PV 2026E",
    lookupBtn: "Parkvorgang suchen",
    demoQuickFill: "Demo-Kennzeichen testen:",
    notFound: "Kein offener oder aktiver Parkvorgang für dieses Kennzeichen gefunden.",
    tariffCardTitle: "Tarifübersicht (Mall-Standard)",
    weekdayFree: "Mo–Fr kostenfrei:",
    weekendFree: "Wochenende (Sa & So):",
    weekendFreeValue: "Ganztägig kostenfrei",
    driveThrough: "Durchfahrts-Kulanz:",
    payLater: "PayLater nach Ausfahrt:",
    entryLabel: "Einfahrt",
    exitLabel: "Ausfahrt",
    durationLabel: "Parkdauer",
    freeApplied: "Freizeit angerechnet",
    billableHours: "Berechnete Stunden",
    netLabel: "Nettobetrag",
    vatLabel: "inkl. 19% MwSt.",
    totalDue: "Offener Betrag",
    freeStayBanner: "Keine Gebühr fällig — Sie können direkt schrankenlos ausfahren.",
    paidBanner: "Parkvorgang vollständig bezahlt — vielen Dank!",
    payMethodLabel: "Zahlungsmethode wählen",
    payNowBtn: "Jetzt bezahlen",
    downloadInvoice: "Rechnung als PDF herunterladen (§ 14 UStG)",
    privacyFooter:
      "DSGVO-Hinweis (Art. 5 & Art. 13 DSGVO): Bei schrankenloser Einfahrt wird ausschließlich das Kennzeichen erfasst. Personen und Fahrzeuginnenräume werden bereits auf dem Edge-Gerät unkenntlich gemacht. Nach regelkonformer Ausfahrt werden Kennzeichen- und Bilddaten automatisiert gelöscht.",
    adminTitle: "Betreiber-Dashboard & DSGVO-Monitor",
    adminSubtitle: "Echtzeit-Belegung, Hybrid-ANPR Kameras, QA-Verstöße, KBA § 39 StVG & DSGVO-Löschung",
    kpiOccupancy: "Auslastung",
    kpiRevenue: "Umsatz (Brutto)",
    kpiCameras: "Kameras Online",
    kpiPurged: "DSGVO Gelöscht",
    lanesTitle: "Hybrid-ANPR Fahrspuren (Edge AI & Smart Webhooks)",
    simulatorTitle: "Live Kamera-Simulator (Fahrzeugdurchfahrt testen)",
    simLane: "Fahrspur",
    simDirection: "Richtung",
    simPlate: "Kennzeichen",
    simVendor: "Kamera-Adapter",
    simMinutesAgo: "Vor (Minuten)",
    simTriggerBtn: "Durchfahrt auslösen",
    reconcileTitle: "OCR-Klärungsliste (Fuzzy-Match Schutz vor Fehlbußen)",
    reconcileEmpty: "Keine offenen OCR-Klärungsfälle.",
    reconcileApprove: "Paar bestätigen",
    reconcileFree: "Kostenfrei schließen",
    sessionsTitle: "Aktuelle & archivierte Parkvorgänge",
    colPlate: "Kennzeichen",
    colStatus: "Status",
    colEntry: "Einfahrt",
    colExit: "Ausfahrt",
    colDuration: "Dauer",
    colFee: "Gebühr",
    purgedPlateLabel: "Anonymisiert (DSGVO Art. 5)",
    dsgvoTitle: "DSGVO-Löschprotokoll (Zero-PII Audit-Log)",
    runPurgeBtn: "DSGVO-Löschlauf sofort starten",
    purgeRunning: "Löschlauf aktiv...",
    auditEmpty: "Noch keine DSGVO-Löschläufe protokolliert.",
    // Sprint 2
    autopayTitle: "AutoPay — Automatisch Ein- & Ausfahren",
    autopaySubtitle:
      "Hinterlegen Sie einmalig Ihr Kennzeichen. Bei Überschreitung der Freiparkzeit wird der fällige Betrag automatisch abgerechnet und Ihr PDF-Beleg erstellt.",
    autopayConsent:
      "Ich willige gemäß Art. 6 Abs. 1 lit. a/b DSGVO in die Speicherung meines Kennzeichens zur automatischen Parkgebühren-Abrechnung ein (jederzeit widerrufbar).",
    autopayRegisterBtn: "AutoPay aktivieren",
    kioskTitle: "Kassenautomat (Touchscreen-Modus)",
    kioskSubtitle: "Tippen Sie Ihr Kennzeichen ein und zahlen Sie kontaktlos per Girocard / NFC",
    validateTitle: "Mieter- & Kino-Validierung (Mall-Portal)",
    validateSubtitle:
      "Scannen Sie den Kinobeleg oder geben Sie das Kundenkennzeichen ein, um sofort +2 Stunden Freiparken oder 100 % VIP-Freigabe gutzuschreiben.",
    disputeTitle: "Widerspruchsportal & Zahlung (Vertragsstrafe)",
    disputeSubtitle:
      "Geben Sie Ihr Aktenzeichen und Kennzeichen ein, um eine Zahlungsaufforderung zu prüfen, direkt zu begleichen, einen Beleg einzureichen oder den tatsächlichen Fahrer zu benennen (BGH sekundäre Darlegungslast).",
    violationsTitle: "Verstöße, Menschliche QA-Prüfung & KBA-Halterabfrage (§ 39 StVG)",
    disputesAdminTitle: "Offene Widersprüche (Widerspruchsportal)",
  },
  en: {
    brandSubtitle: "Barrierless ANPR Parking · GDPR by Design",
    navPay: "Pay",
    navAutoPay: "AutoPay",
    navKiosk: "Kiosk",
    navValidate: "Merchant",
    navDispute: "Dispute",
    navAdmin: "Admin",
    payTitle: "Barrierless Parking — Instant Checkout",
    paySubtitle:
      "Enter your license plate to check your active stay or settle your balance online within the 48-hour PayLater grace window.",
    plateLabel: "License Plate (DE / EU)",
    platePlaceholder: "e.g. M-PV 2026E",
    lookupBtn: "Look Up Stay",
    demoQuickFill: "Try demo plates:",
    notFound: "No active or payable parking session found for this license plate.",
    tariffCardTitle: "Site Tariff Summary (Mall Standard)",
    weekdayFree: "Mon–Fri Free:",
    weekendFree: "Weekends (Sat & Sun):",
    weekendFreeValue: "Free all day",
    driveThrough: "Drive-through Grace:",
    payLater: "PayLater Window:",
    entryLabel: "Entry Time",
    exitLabel: "Exit Time",
    durationLabel: "Duration",
    freeApplied: "Free Allowance Applied",
    billableHours: "Billable Hours",
    netLabel: "Net Amount",
    vatLabel: "incl. 19% German VAT",
    totalDue: "Balance Due",
    freeStayBanner: "No fee due — you may exit freely without stopping.",
    paidBanner: "Parking session settled in full — thank you!",
    payMethodLabel: "Select Payment Method",
    payNowBtn: "Pay Now",
    downloadInvoice: "Download German VAT Invoice (PDF)",
    privacyFooter:
      "GDPR Notice (Art. 5 & Art. 13 GDPR): Only license plates are processed for barrierless contract fulfillment. Faces and vehicle cabins are irreversibly blurred on-edge in RAM. Compliant stays are purged automatically.",
    adminTitle: "Operator Command Center & GDPR Monitor",
    adminSubtitle: "Real-time occupancy, hybrid ANPR cameras, QA violations, KBA § 39 StVG & automated GDPR purging",
    kpiOccupancy: "Occupancy",
    kpiRevenue: "Gross Revenue",
    kpiCameras: "Cameras Online",
    kpiPurged: "GDPR Purged",
    lanesTitle: "Hybrid ANPR Lanes (Edge AI & Smart Camera Webhooks)",
    simulatorTitle: "Live Camera Pass Simulator",
    simLane: "Lane",
    simDirection: "Direction",
    simPlate: "Plate",
    simVendor: "Camera Adapter",
    simMinutesAgo: "Minutes Ago",
    simTriggerBtn: "Trigger Camera Pass",
    reconcileTitle: "OCR Fuzzy Reconciliation Queue (Zero Unfair Fines)",
    reconcileEmpty: "No pending OCR reconciliation items.",
    reconcileApprove: "Approve Pair",
    reconcileFree: "Close Free",
    sessionsTitle: "Active & Recent Parking Sessions",
    colPlate: "Plate",
    colStatus: "Status",
    colEntry: "Entry",
    colExit: "Exit",
    colDuration: "Duration",
    colFee: "Fee",
    purgedPlateLabel: "Anonymized (GDPR Art. 5)",
    dsgvoTitle: "GDPR Auto-Purge Compliance Log (Zero-PII Audit Trail)",
    runPurgeBtn: "Run GDPR Auto-Purge Now",
    purgeRunning: "Purging...",
    auditEmpty: "No GDPR purge runs recorded yet.",
    // Sprint 2
    autopayTitle: "AutoPay — Drive In, Drive Out Seamlessly",
    autopaySubtitle:
      "Link your license plate once. Whenever a stay exceeds the free window, fees are billed automatically on exit with instant German VAT PDF invoices.",
    autopayConsent:
      "I consent under GDPR Art. 6(1)(a)/(b) to storing my license plate for automated parking billing (revocable anytime with one click).",
    autopayRegisterBtn: "Enable AutoPay",
    kioskTitle: "Pay-on-Foot Kiosk (Touchscreen Mode)",
    kioskSubtitle: "Tap your license plate and settle via Girocard / contactless NFC",
    validateTitle: "Mall Tenant & Cinema Validation Portal",
    validateSubtitle:
      "Grant +2h free parking or 100% VIP validation to shoppers and cinema guests in seconds.",
    disputeTitle: "Dispute & Penalty Settlement Portal (Widerspruchsportal)",
    disputeSubtitle:
      "Enter your case number and license plate to settle a penalty notice, submit proof, or nominate the actual driver under German BGH case law.",
    violationsTitle: "Violations, Human QA Review & KBA § 39 StVG Lookup",
    disputesAdminTitle: "Driver Disputes Queue",
  },
} as const;
