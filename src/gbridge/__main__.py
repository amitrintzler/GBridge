"""GBridge entry point — python -m gbridge."""

from __future__ import annotations

import sys

from gbridge.utils.logger import setup_logger

logger = setup_logger(__name__)


def main() -> int:
    logger.info("GBridge starting")
    logger.info("Phase 1: Google sync infrastructure ready. Outlook write-back coming in Phase 2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
