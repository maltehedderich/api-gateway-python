"""Main entry point for the API Gateway."""

import asyncio
import logging
import sys

from gateway.core.config import load_config
from gateway.core.gateway import Gateway


def setup_logging(log_level: str = "INFO") -> None:
    """Setup basic logging configuration.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )


async def main() -> None:
    """Main entry point."""
    try:
        # Load configuration
        config = load_config()

        # Setup logging
        setup_logging(config.logging.level)

        logger = logging.getLogger(__name__)
        logger.info("Initializing API Gateway...")

        # Create and run gateway
        gateway = Gateway(config)
        await gateway.run_forever()

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
