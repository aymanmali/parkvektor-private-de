import csv
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from io import StringIO


@dataclass(frozen=True)
class KeeperLookupRequest:
    case_number: str
    plate_normalized: str
    plate_country: str
    incident_timestamp: datetime
    site_name: str
    legal_basis: str = "§ 39 Abs. 1 StVG (Geltendmachung zivilrechtlicher Ansprüche aus Parknutzungsvertrag)"


@dataclass(frozen=True)
class KeeperLookupResult:
    provider: str
    request_ref: str
    status: str  # RESOLVED | QUEUED_BATCH | NOT_FOUND
    keeper_name: str | None = None
    keeper_address: str | None = None


class KeeperLookupProvider(ABC):
    """Pluggable § 39 StVG / ZFZR KBA keeper lookup adapter."""

    @abstractmethod
    def request_keeper(self, req: KeeperLookupRequest) -> KeeperLookupResult:
        """Initiate or resolve a German KBA keeper inquiry."""


class MockKBAProvider(KeeperLookupProvider):
    """Deterministic local/staging KBA mock for testing violation & dispute flows."""

    def request_keeper(self, req: KeeperLookupRequest) -> KeeperLookupResult:
        return KeeperLookupResult(
            provider="mock_kba",
            request_ref=f"KBA-MOCK-{uuid.uuid4().hex[:10].upper()}",
            status="RESOLVED",
            keeper_name="Max Mustermann (Test-Halter)",
            keeper_address="Musterstraße 42, 80000 Musterstadt, DE",
        )


class BatchCSVKBAProvider(KeeperLookupProvider):
    """
    Production bridge for German licensed KBA / Inkasso bureaus prior to direct ZFZR API credentials.
    Exports compliant § 39 StVG request batches as semicolon-delimited German CSV.
    """

    def request_keeper(self, req: KeeperLookupRequest) -> KeeperLookupResult:
        return KeeperLookupResult(
            provider="batch_csv_kba",
            request_ref=f"KBA-BATCH-{uuid.uuid4().hex[:10].upper()}",
            status="QUEUED_BATCH",
        )

    @staticmethod
    def build_csv_batch(requests: list[KeeperLookupRequest]) -> str:
        buf = StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(["Aktenzeichen", "Kennzeichen", "Land", "Tatzeit_UTC", "Standort", "Rechtsgrundlage"])
        for r in requests:
            writer.writerow(
                [
                    r.case_number,
                    r.plate_normalized,
                    r.plate_country,
                    r.incident_timestamp.isoformat(),
                    r.site_name,
                    r.legal_basis,
                ]
            )
        return buf.getvalue()
