import argparse
from app.config import settings
from app.services.maintenance import run_maintenance


def main() -> None:
    parser = argparse.ArgumentParser(description="Market Sentiment 2 CLI tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    maint_parser = subparsers.add_parser("maintenance", help="Run database maintenance tasks")
    maint_parser.add_argument(
        "--vacuum",
        action="store_true",
        default=False,
        help="Execute database VACUUM after purging",
    )
    maint_parser.add_argument(
        "--retention-days",
        type=int,
        default=settings.RUN_RETENTION_DAYS,
        help=f"Data retention window in days (default: {settings.RUN_RETENTION_DAYS})",
    )

    args = parser.parse_args()

    if args.command == "maintenance":
        res = run_maintenance(
            retention_days=args.retention_days,
            vacuum=args.vacuum,
        )
        print(
            f"Maintenance complete: "
            f"expired jobs deleted: {res['expired_jobs_deleted']}, "
            f"old runs deleted: {res['old_runs_deleted']}, "
            f"vacuumed: {res['vacuumed']}"
        )


if __name__ == "__main__":
    main()
