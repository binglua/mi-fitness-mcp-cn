"""Sync service for importing data from adapters to database."""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta
from typing import Any

from mi_fitness_mcp.adapters.base import DataAdapter
from mi_fitness_mcp.storage import Database

logger = logging.getLogger(__name__)


class SyncService:
    """Service for synchronizing data from adapters to local database."""

    def __init__(self, adapter: DataAdapter, db: Database):
        """Initialize sync service.
        
        Args:
            adapter: Data source adapter
            db: Database instance
        """
        self.adapter = adapter
        self.db = db

    async def _iterate_records(self, records: Any) -> AsyncIterator[Any]:
        if hasattr(records, "__aiter__"):
            async for record in records:
                yield record
            return

        for record in records:
            yield record

    async def sync_data_type(
        self,
        data_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
        force_full: bool = False,
    ) -> dict:
        """Synchronize a specific data type.
        
        Args:
            data_type: Type of data to sync (daily_activity, sleep, workouts, body_measurements)
            start_date: Start date (YYYY-MM-DD), defaults to 30 days ago
            end_date: End date (YYYY-MM-DD), defaults to today
            force_full: Force full sync ignoring last sync state
            
        Returns:
            Dict with sync statistics
        """
        if not self.adapter.is_connected():
            raise RuntimeError("Adapter not connected")

        # Get last sync state for incremental sync
        last_record_ts = None
        if not force_full:
            state = self.db.get_sync_state(data_type)
            if state and state.get("last_record_timestamp"):
                last_record_ts = datetime.fromisoformat(state["last_record_timestamp"])

        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            if last_record_ts:
                start_date = last_record_ts.strftime("%Y-%m-%d")
            elif self.adapter.__class__.__name__ == "MiFitnessCloudAdapter":
                start_date = "2020-01-01"
            else:
                start = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=30)
                start_date = start.strftime("%Y-%m-%d")

        added = 0
        updated = 0
        skipped = 0
        last_ts = None

        # Sync based on data type
        if data_type == "daily_activity":
            records = self.adapter.iter_daily_activity(start_date, end_date)
            async for activity in self._iterate_records(records):
                if self.db.insert_daily_activity(activity):
                    added += 1
                else:
                    updated += 1
                if last_ts is None or (activity.collected_at and activity.collected_at > last_ts):
                    last_ts = activity.collected_at

        elif data_type == "sleep":
            records = self.adapter.iter_sleep_sessions(start_date, end_date)
            async for sleep in self._iterate_records(records):
                if self.db.insert_sleep_session(sleep):
                    added += 1
                else:
                    updated += 1
                if last_ts is None or sleep.start_at > last_ts:
                    last_ts = sleep.start_at

        elif data_type == "workouts":
            records = self.adapter.iter_workouts(start_date, end_date)
            async for workout in self._iterate_records(records):
                if self.db.insert_workout(workout):
                    added += 1
                else:
                    updated += 1
                if last_ts is None or workout.start_at > last_ts:
                    last_ts = workout.start_at

        elif data_type == "body_measurements":
            records = self.adapter.iter_body_measurements(start_date, end_date)
            async for measurement in self._iterate_records(records):
                if self.db.insert_body_measurement(measurement):
                    added += 1
                else:
                    updated += 1
                if last_ts is None or measurement.timestamp > last_ts:
                    last_ts = measurement.timestamp

        elif data_type == "heart_rate":
            records = self.adapter.iter_heart_rate(start_date, end_date)
            async for sample in self._iterate_records(records):
                if self.db.insert_heart_rate_sample(sample):
                    added += 1
                else:
                    updated += 1
                if last_ts is None or sample.timestamp > last_ts:
                    last_ts = sample.timestamp

        else:
            raise ValueError(f"Unknown data type: {data_type}")

        # Update sync state
        if last_ts:
            self.db.update_sync_state(data_type, last_ts)

        logger.info(
            f"Synced {data_type}: {added} added, {updated} updated, "
            f"range {start_date} to {end_date}"
        )

        return {
            "data_type": data_type,
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "start_date": start_date,
            "end_date": end_date,
        }

    def sync_data_type_sync(
        self,
        data_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
        force_full: bool = False,
    ) -> dict:
        """Synchronous wrapper for sync_data_type.
        
        Use this when calling from synchronous code.
        """
        return asyncio.run(self.sync_data_type(data_type, start_date, end_date, force_full))
