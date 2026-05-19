from pathlib import Path
from urllib.parse import urlparse

import structlog

from sift.extractors.base import ExtractFailure, ExtractResult, get_extractor

logger = structlog.get_logger()


def dispatch_extract(url: str, work_dir: Path) -> ExtractResult | ExtractFailure:
    hostname = urlparse(url).netloc.lower()
    extractor = get_extractor(hostname)
    if extractor is None:
        return ExtractFailure(
            url=url,
            platform="unknown",
            error_class="site-changed",
            error_detail=f"No extractor registered for hostname '{hostname}'",
            suggested_t2="Register an extractor for this platform or open an issue.",
        )

    try:
        return extractor.extract(url, work_dir)
    except Exception as e:  # noqa: BLE001 — extractors raise diverse errors
        logger.warning(
            "extractor-failed",
            url=url,
            platform=extractor.platform,
            error=str(e),
        )
        return ExtractFailure(
            url=url,
            platform=extractor.platform,
            error_class="unknown",
            error_detail=str(e),
        )
