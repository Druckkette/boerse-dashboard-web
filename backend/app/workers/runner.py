import argparse
import json
from datetime import UTC, datetime


def run_dummy_job(job_type: str) -> dict:
    return {
        "ok": True,
        "job_type": job_type,
        "message": "Dummy job completed. Real market refreshes will be attached in later phases.",
        "finished_at": datetime.now(UTC).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Boerse dashboard worker scaffold.")
    parser.add_argument("--job-type", default="noop")
    args = parser.parse_args()
    print(json.dumps(run_dummy_job(args.job_type), indent=2))


if __name__ == "__main__":
    main()

