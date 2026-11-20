# Technische Checkliste: Datenschutz-Folgenabschätzung (DSFA / Art. 35 DSGVO)

Diese Checkliste dokumentiert die **Privacy-by-Design**-Kontrollen von `parkvektor-private-de` für die Freigabe durch einen deutschen Datenschutzbeauftragten vor Produktivbetrieb.

- [x] **Datenminimierung (Art. 5 Abs. 1 lit. c):** Keine kontinuierliche Videoaufzeichnung; Speicherung ausschließlich von Kennzeichen-Crop + unveränderlich geschwärztem/verpixeltem Kontextbild pro Ein-/Ausfahrt.
- [x] **On-Edge Unkenntlichmachung:** Gesichter, Fußgänger, Windschutzscheiben-Bereich (obere 55–60 %) und unbeteiligte Nachbarkennzeichen werden **im Arbeitsspeicher (RAM)** irreversibel verpixelt & weichgezeichnet, bevor ein JPEG kodiert oder übertragen wird (`edge/pipeline/redactor.py`).
- [x] **Server-Side Redaction Fallback:** Für Smart-ANPR-Kameras ohne eigene Privacy-Maske greift der verpflichtende Server-Fallback (`backend/app/adapters/cameras/redactor.py`).
- [x] **Speicherbegrenzung & Auto-Purge (Art. 5 Abs. 1 lit. e):** Automatisierter Worker (`app/workers/purge_worker.py`) löscht Kennzeichenfelder und S3-Bilddateien nach Ablauf der konfigurierten Frist (≤ 24h) physisch und unwiderruflich.
- [x] **Entkopplung Steuerrecht (§ 147 AO) vs. DSGVO:** PDF-Rechnungen (`app/domain/invoices.py`) enthalten keine Kamerabilder und erlauben die getrennte 8-jährige GoBD-Aufbewahrung bei gleichzeitiger Löschung der ANPR-Rohdaten.
- [x] **Zero-PII Löschprotokoll:** `dsgvo_purge_audit_log` protokolliert Löschvorgänge revisionssicher **ohne** das gelöschte Kennzeichen erneut zu speichern.
- [x] **Betroffenenrechte (Art. 15 & Art. 17):** Dedizierte Admin-Schnittstellen für Auskunft (`GET /api/v1/admin/dsgvo/export`) und Löschung (`DELETE /api/v1/admin/dsgvo/erase` unter Beachtung von Art. 17 Abs. 3).
- [x] **Transportsicherheit & EU-Datenresidenz:** HMAC-SHA256-signierte Edge-Ingestion über TLS; Zielbetrieb in deutschen Rechenzentren (Frankfurt / Hetzner DE).
- [ ] **Organisatorisch (vor Live-Start pro Standort):** Auftragsverarbeitungsvertrag (AVV nach Art. 28 DSGVO) mit Cloud-Hoster & Payment-Provider abschließen, Art.-13-Einfahrtsschilder fotodokumentieren, DSFA formell durch den DSB abzeichnen lassen.
