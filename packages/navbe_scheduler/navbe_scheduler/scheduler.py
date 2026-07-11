import re
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from croniter import croniter

_RELATIVE_RE = re.compile(r"^\+(\d+)([smhd])$")

_UNIT_TO_KWARG = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
}

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_WEEKDAY_RE = re.compile(
    r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"(?:\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?$"
)


class ScheduleParser:
    @staticmethod
    def parse(when: str) -> datetime:
        when = when.strip().lower()

        relative_match = _RELATIVE_RE.match(when)
        if relative_match:
            amount, unit = relative_match.groups()
            delta = timedelta(**{_UNIT_TO_KWARG[unit]: int(amount)})
            return datetime.utcnow() + delta

        weekday_match = _WEEKDAY_RE.match(when)
        if weekday_match:
            day_name, hour, minute, meridiem = weekday_match.groups()
            return ScheduleParser._next_weekday_at(day_name, hour, minute, meridiem)

        if croniter.is_valid(when):
            return croniter(when, datetime.utcnow()).get_next(datetime)

        raise ValueError(f"Unrecognized schedule format: {when!r}")

    @staticmethod
    def is_cron(when: str) -> bool:
        when = when.strip().lower()
        if _RELATIVE_RE.match(when) or _WEEKDAY_RE.match(when):
            return False
        return croniter.is_valid(when)

    @staticmethod
    def _next_weekday_at(day_name: str, hour: str, minute: str, meridiem: str) -> datetime:
        target_hour = int(hour) if hour is not None else 9
        target_minute = int(minute) if minute is not None else 0

        if meridiem == "pm" and target_hour != 12:
            target_hour += 12
        elif meridiem == "am" and target_hour == 12:
            target_hour = 0

        now = datetime.utcnow()
        target_weekday = _WEEKDAYS[day_name]
        days_ahead = (target_weekday - now.weekday()) % 7

        candidate = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        candidate += timedelta(days=days_ahead)

        if candidate <= now:
            candidate += timedelta(days=7)

        return candidate


class APSchedulerAdapter:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        self.scheduler.start()

    def register(self, workflow_id: str, run_at: datetime, callback: Callable) -> None:
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UTC)

        self.scheduler.add_job(
            callback,
            trigger="date",
            run_date=run_at,
            args=[workflow_id],
            id=workflow_id,
            replace_existing=True,
        )

    def cancel(self, workflow_id: str) -> None:
        with suppress(Exception):
            self.scheduler.remove_job(workflow_id)

    def load_existing(self, workflows: list, callback: Callable) -> None:
        for w in workflows:
            if w.scheduled_at > datetime.utcnow():
                self.register(w.id, w.scheduled_at, callback)
