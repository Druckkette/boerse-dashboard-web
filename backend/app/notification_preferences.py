"""Validated, user-editable notification preferences shared by API and workers."""
from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


NotificationMode = Literal["off", "digest", "immediate"]
NotificationSession = Literal["all", "regular", "custom"]
NotificationPriority = Literal[-1, 0, 1]
RepeatMode = Literal["daily", "manual", "recovery", "interval"]
NotificationCategory = Literal["ma", "score", "verdict", "stop", "atr"]
MAKey = Literal["sma10", "ema21", "sma50", "sma200"]


class PreferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MANotificationRule(PreferenceModel):
    break_mode: NotificationMode = "digest"
    recovery_mode: NotificationMode = "digest"
    worsening_mode: NotificationMode = "digest"
    confirmation: Literal["intraday", "close"] = "intraday"
    confirmation_minutes: int = Field(default=10, ge=1, le=1440)
    distance_unit: Literal["atr", "pct"] = "atr"
    min_distance: float = Field(default=0.2, ge=0.01, le=20)
    worsening_atr: float = Field(default=1, ge=0.01, le=20)
    max_per_day: int = Field(default=1, ge=0, le=100)
    session: NotificationSession = "regular"
    priority: NotificationPriority = 0


class StopNotificationRule(PreferenceModel):
    mode: NotificationMode = "immediate"
    repeat: RepeatMode = "daily"
    repeat_minutes: int = Field(default=60, ge=1, le=1440)
    recovery_pct: float = Field(default=1, ge=0.01, le=20)
    recovery_minutes: int = Field(default=10, ge=1, le=1440)
    priority: NotificationPriority = 1
    session: NotificationSession = "all"


class ATRNotificationRule(PreferenceModel):
    mode: NotificationMode = "immediate"
    escalation_enabled: bool = True
    escalation_atr: float = Field(default=3, ge=0.5, le=20)
    repeat: RepeatMode = "daily"
    repeat_minutes: int = Field(default=60, ge=1, le=1440)
    recovery_atr: float = Field(default=1, ge=0, le=10)
    recovery_minutes: int = Field(default=10, ge=1, le=1440)
    priority: NotificationPriority = 1
    session: NotificationSession = "all"


class AssessmentNotificationRule(PreferenceModel):
    score_mode: NotificationMode = "digest"
    verdict_mode: NotificationMode = "digest"
    score_min_change: int = Field(default=10, ge=1, le=100)
    notify_improvements: bool = True
    notify_deteriorations: bool = True
    priority: NotificationPriority = 0
    session: NotificationSession = "regular"


class NotificationGrouping(PreferenceModel):
    enabled: bool = True
    window_minutes: int = Field(default=30, ge=1, le=1440)
    max_immediate_per_ticker_day: int = Field(default=3, ge=0, le=100)
    stop_bypass: bool = True
    atr_escalation_bypass: bool = True


class NotificationSummary(PreferenceModel):
    enabled: bool = True
    time: str = Field(default="22:45", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    categories: list[NotificationCategory] = Field(default_factory=lambda: ["ma", "score", "verdict", "stop", "atr"])
    include_sent: bool = False
    only_changes: bool = True
    max_tickers: int = Field(default=5, ge=1, le=50)
    priority: NotificationPriority = 0

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[NotificationCategory]) -> list[NotificationCategory]:
        return list(dict.fromkeys(value))


class NotificationQuietHours(PreferenceModel):
    enabled: bool = False
    start: str = Field(default="22:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="07:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    stop_bypass: bool = True
    atr_escalation_bypass: bool = True


class NotificationCustomSession(PreferenceModel):
    start: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="22:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def default_ma_rules() -> dict[MAKey, MANotificationRule]:
    return {
        "sma10": MANotificationRule(),
        "ema21": MANotificationRule(),
        "sma50": MANotificationRule(break_mode="immediate"),
        "sma200": MANotificationRule(break_mode="immediate"),
    }


class NotificationPreferences(PreferenceModel):
    version: Literal[1] = 1
    timezone: str = "Europe/Berlin"
    ma: dict[MAKey, MANotificationRule] = Field(default_factory=default_ma_rules)
    stop: StopNotificationRule = Field(default_factory=StopNotificationRule)
    atr: ATRNotificationRule = Field(default_factory=ATRNotificationRule)
    assessment: AssessmentNotificationRule = Field(default_factory=AssessmentNotificationRule)
    grouping: NotificationGrouping = Field(default_factory=NotificationGrouping)
    summary: NotificationSummary = Field(default_factory=NotificationSummary)
    quiet: NotificationQuietHours = Field(default_factory=NotificationQuietHours)
    custom_session: NotificationCustomSession = Field(default_factory=NotificationCustomSession)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Bitte eine gültige Zeitzone auswählen.") from exc
        return value


def merge_preferences(current: dict, patch: dict) -> dict:
    """Merge a partial API update without resetting other notification choices."""
    merged = dict(current)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_preferences(merged[key], value)
        else:
            merged[key] = value
    return merged
