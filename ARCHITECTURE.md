# Architecture Specification — `parkvektor-private-de`

> Private Barrierless ANPR Parking & Ticketing Platform for Germany (Shopping Mall & Retail Park Reference Architecture).
> 100% standalone repository — zero cross-repository dependencies.

---

## 1. High-Level System Architecture

```mermaid
flowchart TD
    subgraph Site ["Physical Parking Site (Garage / Mall / Retail Lot)"]
        C1["RTSP/ONVIF Cameras (Entry & Exit)"]
        C2["Smart ANPR Cameras (Axis / ARH / Hikvision)"]
        Edge["Edge AI Node (YOLO + DE/EU OCR + On-Edge Blur + SQLite Offline Buffer)"]
        Kiosk["Pay-on-Foot Kiosk (Touchscreen + Stripe Terminal)"]
        C1 --> Edge
    end

    subgraph Cloud ["German/EU Cloud Backend (Frankfurt / Hetzner DE)"]
        API["FastAPI Core API (Auth, Webhooks, Sessions, Tariffs, Violations)"]
        Workers["Background Workers (DSGVO Purge, PayLater Expiry, AutoPay, PDF Invoices)"]
        PG[("PostgreSQL (Transactional + Anonymized Analytics)")]
        Redis[("Redis (Queues & Locks)")]
        S3[("EU S3 / MinIO (Encrypted Short-Lived Crops & GoBD Invoices)")]

        Edge -->|"HTTPS + HMAC/mTLS (Plate + Blurred Crop)"| API
        C2 -->|"Signed Webhook"| API
        API <--> PG
        API <--> Redis
        API <--> S3
        Workers <--> PG
        Workers <--> Redis
        Workers <--> S3
    end

    subgraph External ["Pluggable External Adapters"]
        Stripe["PaymentProvider (Stripe: SEPA, Apple/Google Pay, PayPal, Cards)"]
        KBA["KeeperLookupProvider (Mock / Batch Inkasso CSV / KBA § 39 StVG API)"]
    end

    subgraph Web ["Next.js Web Portals (German Default / English)"]
        DriverPay["Driver QR Checkout & AutoPay Portal"]
        Merchant["Mall Tenant Validation Portal (+2h Cinema / Retail)"]
        Dispute["Widerspruchsportal (Disputes & Fahrerbenennung)"]
        Admin["Operator Dashboard & Violation QA Queue"]
    end

    API <--> Stripe
    Workers <--> KBA
    Kiosk <--> API
    Web <--> API
```

---

## 2. Database Schema & DSGVO Decoupling

To satisfy both **DSGVO Art. 5(1)(e)** (short retention & auto-deletion of compliant plates/photos) and **German Tax Law (`§ 147 AO`)** (8-year invoice voucher retention), ephemeral PII is strictly decoupled from accounting invoices and anonymized operational telemetry.

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ SITES : owns
    SITES ||--o{ LANES : has
    SITES ||--o{ TARIFF_PLANS : configures
    SITES ||--o{ WHITELISTS : permits
    SITES ||--o{ MERCHANT_ACCOUNTS : hosts
    SITES ||--o{ PARKING_SESSIONS : tracks
    SITES ||--o{ DAILY_SITE_ANALYTICS : aggregates

    LANES ||--o{ CAMERA_EVENTS : captures
    CAMERA_EVENTS ||--o| PARKING_SESSIONS : "entry / exit"

    PARKING_SESSIONS ||--o{ SESSION_VALIDATIONS : receives
    MERCHANT_ACCOUNTS ||--o{ SESSION_VALIDATIONS : grants
    PARKING_SESSIONS ||--o{ PAYMENTS : settled_by
    PAYMENTS ||--o| INVOICES : generates
    PARKING_SESSIONS ||--o| VIOLATIONS : escalates_to
    VIOLATIONS ||--o{ DISPUTES : contested_by

    DRIVER_ACCOUNTS ||--o{ AUTOPAY_VEHICLES : registers
    DRIVER_ACCOUNTS ||--o{ PAYMENTS : pays
```

---

## 3. DSGVO Data Lifecycle & Retention Rules

```mermaid
stateDiagram-v2
    [*] --> EdgeRAM : "Camera captures vehicle pass"
    EdgeRAM --> Discarded : "Noise / non-vehicle (0s storage)"
    EdgeRAM --> ActiveSession : "Blur faces & bystanders in RAM, upload plate + crop"

    ActiveSession --> CleanFreeExit : "Exit within free window / whitelist / validated"
    ActiveSession --> PaidExit : "Paid via AutoPay / Kiosk / QR before exit"
    ActiveSession --> PayLaterWindow : "Exit with balance due (24-48h grace)"

    PayLaterWindow --> PaidExit : "Driver pays online via plate lookup"
    PayLaterWindow --> QAReview : "Grace period expires unpaid"

    CleanFreeExit --> Purged : "Auto-Purge Worker (Immediate to <=24h)"
    PaidExit --> Purged : "Purge plate & S3 crops (<=24-48h); keep invoice only"

    QAReview --> Purged : "Operator rejects (OCR error / invalid) -> Immediate purge"
    QAReview --> ViolationActive : "Operator confirms violation -> KBA § 39 StVG lookup"

    ViolationActive --> CaseClosed : "Paid / Dispute accepted / Settled"
    CaseClosed --> Purged : "Purge evidence & keeper PII after closure window"
    Purged --> [*] : "Write zero-PII record to dsgvo_purge_audit_log"
```

---

## 4. Repository Structure

```text
parkvektor-private-de/
├── backend/         # FastAPI + SQLAlchemy 2.0 + Alembic + DSGVO purge & Stripe adapters
├── edge/            # Standalone Edge AI Node (ONNX/YOLO, DE/EU OCR voter, RAM DSGVO redactor, SQLite WAL)
├── frontend/        # Next.js (TypeScript + Tailwind, DE default / EN toggle)
├── tools/           # German plate image generator & camera webhook/edge simulator
├── infra/           # Dockerfiles + German Art. 13 entrance signage & DPIA (DSFA) templates
└── .github/workflows/
```
