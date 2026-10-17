"""Bounded concurrent lookup of unknown instruments, once per distinct ISIN."""
from concurrent.futures import ThreadPoolExecutor, wait

from app.data_sources.isin_search import search_isin


def complete_mappings(diagnostics: list[dict], *, open_isins: set[str] | None = None) -> list[dict]:
    missing = sorted(
        (item for item in diagnostics if not item.get("ticker")),
        key=lambda item: item["isin"] not in (open_isins or set()),
    )
    if not missing:
        return diagnostics
    pool = ThreadPoolExecutor(max_workers=4)
    futures = {pool.submit(search_isin, item["isin"], item["asset_class"]): item["isin"] for item in missing}
    try:
        # Stay below the frontend's 45s request deadline, even for a large
        # first import or unavailable provider. Open holdings run first.
        done, _ = wait(futures, timeout=20)
        resolved = {futures[future]: future.result() for future in done}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    deferred = {"ticker": "", "candidates": [], "message": "Suchzeit erreicht. Vorschau erneut prüfen oder Ticker einmalig ergänzen."}
    return [
        {**item, **resolved.get(item["isin"], deferred), "source": "automatic" if resolved.get(item["isin"], {}).get("ticker") else "missing"}
        if not item.get("ticker") else item
        for item in diagnostics
    ]
