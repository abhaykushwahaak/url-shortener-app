"""Analytics response models."""

from datetime import date

from pydantic import BaseModel, Field


class CountByKey(BaseModel):
    """A labelled count - used for device, browser and referrer breakdowns."""

    key: str
    count: int


class TimelinePoint(BaseModel):
    date: date
    clicks: int


class AnalyticsSummary(BaseModel):
    url_id: str
    short_code: str
    original_url: str
    total_clicks: int
    clicks_today: int = 0
    clicks_this_week: int = 0
    unique_visitors: int = Field(0, description="Distinct IP addresses observed")
    first_click_at: str | None = None
    last_click_at: str | None = None
    devices: list[CountByKey] = []
    browsers: list[CountByKey] = []
    referrers: list[CountByKey] = []
    countries: list[CountByKey] = []


class TimelineResponse(BaseModel):
    url_id: str
    days: int
    points: list[TimelinePoint]


class TopURL(BaseModel):
    url_id: str
    short_code: str
    original_url: str
    clicks: int