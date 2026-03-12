"""Background sync scheduler for Mi Fitness MCP."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable

from mi_fitness_mcp.adapters.base import DataAdapter
from mi_fitness_mcp.storage import Database

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Scheduler for automatic background synchronization."""

    def __init__(
        self,
        adapter: DataAdapter,
        db: Database,
        sync_interval_minutes: int = 60,
    ):
        """Initialize sync scheduler.
        
        Args:
            adapter: Data source adapter
            db: Database instance
            sync_interval_minutes: How often to sync (default: 1 hour)
        """
        self.adapter = adapter
        self.db = db
        self.sync_interval = timedelta(minutes=sync_interval_minutes)
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_sync: datetime | None = None
        self._sync_callback: Callable | None = None

    def set_sync_callback(self, callback: Callable) -> None:
        """Set callback to be called after each sync.
        
        Args:
            callback: Function to call with sync results
        """
        self._sync_callback = callback

    async def start(self) -> None:
        """Start the sync scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info(f"Sync scheduler started (interval: {self.sync_interval})")

    async def stop(self) -> None:
        """Stop the sync scheduler."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Sync scheduler stopped")

    async def _run_scheduler(self) -> None:
        """Main scheduler loop."""
        from mi_fitness_mcp.services.sync_service import SyncService
        
        sync_service = SyncService(self.adapter, self.db)
        
        while self._running:
            try:
                # Check if it's time to sync
                if self._should_sync():
                    await self._perform_sync(sync_service)
                
                # Wait for next check
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sync scheduler: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    def _should_sync(self) -> bool:
        """Check if sync should be performed."""
        if not self._last_sync:
            return True
        
        time_since_last = datetime.utcnow() - self._last_sync
        return time_since_last >= self.sync_interval

    async def _perform_sync(self, sync_service) -> None:
        """Perform synchronization of all data types."""
        logger.info("Starting automatic sync")
        
        results = {}
        data_types = self.adapter.get_available_data_types()
        
        for data_type in data_types:
            try:
                result = sync_service.sync_data_type(data_type)
                results[data_type] = result
                logger.info(
                    f"Synced {data_type}: {result['added']} added, "
                    f"{result['updated']} updated"
                )
            except Exception as e:
                logger.error(f"Failed to sync {data_type}: {e}")
                results[data_type] = {"error": str(e)}
        
        self._last_sync = datetime.utcnow()
        
        # Call callback if set
        if self._sync_callback:
            try:
                self._sync_callback(results)
            except Exception as e:
                logger.error(f"Sync callback failed: {e}")
        
        logger.info("Automatic sync completed")

    def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            "running": self._running,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "sync_interval_minutes": self.sync_interval.total_seconds() / 60,
            "next_sync": (
                (self._last_sync + self.sync_interval).isoformat()
                if self._last_sync
                else None
            ),
        }


class AutoSyncManager:
    """Manager for automatic synchronization configuration."""

    def __init__(self, config_path: str = "config/autosync.json"):
        """Initialize auto-sync manager.
        
        Args:
            config_path: Path to autosync configuration file
        """
        self.config_path = config_path
        self._scheduler: SyncScheduler | None = None

    def load_config(self) -> dict:
        """Load auto-sync configuration."""
        import json
        from pathlib import Path
        
        path = Path(self.config_path)
        if not path.exists():
            return {
                "enabled": False,
                "sync_interval_minutes": 60,
                "data_types": ["daily_activity", "sleep", "workouts"],
            }
        
        with open(path, "r") as f:
            return json.load(f)

    def save_config(self, config: dict) -> None:
        """Save auto-sync configuration."""
        import json
        from pathlib import Path
        
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w") as f:
            json.dump(config, f, indent=2)

    async def start_scheduler(
        self,
        adapter: DataAdapter,
        db: Database,
    ) -> SyncScheduler | None:
        """Start scheduler with loaded configuration.
        
        Args:
            adapter: Data source adapter
            db: Database instance
            
        Returns:
            SyncScheduler instance or None if not enabled
        """
        config = self.load_config()
        
        if not config.get("enabled", False):
            logger.info("Auto-sync is disabled")
            return None
        
        interval = config.get("sync_interval_minutes", 60)
        
        self._scheduler = SyncScheduler(
            adapter=adapter,
            db=db,
            sync_interval_minutes=interval,
        )
        
        await self._scheduler.start()
        return self._scheduler

    async def stop_scheduler(self) -> None:
        """Stop the running scheduler."""
        if self._scheduler:
            await self._scheduler.stop()
            self._scheduler = None

    def get_scheduler_status(self) -> dict | None:
        """Get current scheduler status."""
        if not self._scheduler:
            return None
        return self._scheduler.get_status()
