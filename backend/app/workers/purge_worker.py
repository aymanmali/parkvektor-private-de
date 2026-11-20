import argparse
import time

from app.adapters.storage.factory import get_storage_adapter
from app.db.session import SessionLocal
from app.domain.retention import run_dsgvo_auto_purge
from app.domain.violations import escalate_overdue_sessions


def run_once(force_immediate: bool = False) -> None:
    storage = get_storage_adapter()
    with SessionLocal() as db:
        esc = escalate_overdue_sessions(db)
        summary = run_dsgvo_auto_purge(db, storage, force_immediate=force_immediate)
        print(
            f"[Compliance Worker] {summary.ran_at.isoformat()} | "
            f"escalated_qa={esc.escalated_count} purged={summary.sessions_purged} "
            f"s3_deleted={summary.s3_objects_deleted} events_anonymized={summary.events_anonymized}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="ParkVektor DSGVO Art. 5(1)(e) Retention Purge Worker")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Loop interval in seconds (0 = run once)")
    parser.add_argument("--force-immediate", action="store_true", help="Purge all settled compliant sessions immediately")
    args = parser.parse_args()

    if args.interval_seconds <= 0:
        run_once(force_immediate=args.force_immediate)
        return

    while True:
        run_once(force_immediate=args.force_immediate)
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
