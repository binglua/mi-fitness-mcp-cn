"""Base adapter interface for data sources."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, Coroutine, Union

from mi_fitness_mcp.models import (
    BodyMeasurement,
    DailyActivity,
    HeartRateSample,
    SleepSession,
    Workout,
)


class DataAdapter(ABC):
    """Abstract base class for data source adapters."""

    @abstractmethod
    def connect(self) -> Union[bool, "Coroutine[Any, Any, bool]"]:
        """Connect to data source.
        
        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to data source."""
        pass

    @abstractmethod
    def get_user_id(self) -> str | None:
        """Get user identifier from data source."""
        pass

    @abstractmethod
    def iter_daily_activity(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Union[Iterator[DailyActivity], AsyncIterator[DailyActivity]]:
        """Iterate over daily activity records."""
        pass

    @abstractmethod
    def iter_sleep_sessions(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Union[Iterator[SleepSession], AsyncIterator[SleepSession]]:
        """Iterate over sleep session records."""
        pass

    @abstractmethod
    def iter_workouts(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Union[Iterator[Workout], AsyncIterator[Workout]]:
        """Iterate over workout records."""
        pass

    @abstractmethod
    def iter_body_measurements(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Union[Iterator[BodyMeasurement], AsyncIterator[BodyMeasurement]]:
        """Iterate over body measurement records."""
        pass

    @abstractmethod
    def iter_heart_rate(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Union[Iterator[HeartRateSample], AsyncIterator[HeartRateSample]]:
        """Iterate over heart rate records."""
        pass

    @abstractmethod
    def get_available_data_types(self) -> list[str]:
        """Get list of available data types."""
        pass
