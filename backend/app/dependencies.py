from functools import lru_cache

from app.core.config import get_settings
from app.services.run_store import RunStore


@lru_cache
def get_run_store() -> RunStore:
    settings = get_settings()
    store = RunStore(settings.runs_dir)
    store.cleanup_expired(settings.run_ttl_hours)
    return store
