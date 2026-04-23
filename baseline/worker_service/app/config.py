"""
Worker Service configuration.

Extends base settings with queue and model service connection details.
"""

from shared.config import BaseServiceSettings
from shared.constants import DEFAULT_MODEL_SERVICE_URL


class WorkerServiceSettings(BaseServiceSettings):
    """Configuration for the Worker Service."""

    service_name: str = "worker-service"

    # Model service connection (for processing jobs)
    model_service_url: str = DEFAULT_MODEL_SERVICE_URL

    # Queue configuration
    # "postgres" is the baseline default — durable across restarts.
    # "memory" is kept for quick-start demos with no DB dependency.
    # "redis" is deferred to Task 8 (Load Balancing & Caching).
    queue_type: str = "postgres"
    redis_url: str = "redis://localhost:6379/0"

    # Worker behavior
    poll_interval: float = 1.0  # seconds between queue polls

    model_config = {
        "env_file": "../../.env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
