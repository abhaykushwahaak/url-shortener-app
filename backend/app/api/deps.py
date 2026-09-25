"""Shared FastAPI dependencies (pagination and client metadata)."""

from dataclasses import dataclass

from fastapi import Query, Request


@dataclass
class Pagination:
    page: int
    limit: int
    offset: int

    @property
    def skip(self) -> int:
        return self.offset


def pagination_params(
    page: int = Query(1, ge=1, description="1-based page number"),
    limit: int = Query(
        10, ge=1, le=100, description="Items per page (maximum 100)"
    ),
) -> Pagination:
    """Reusable `?page=&limit=` dependency with a hard cap on `limit`."""
    return Pagination(page=page, limit=limit, offset=(page - 1) * limit)


def client_ip(request: Request) -> str | None:
    """Best-effort client IP.

    `X-Forwarded-For` is honoured for deployments behind a reverse proxy. Note
    that the header is client-controlled when there is no trusted proxy in front,
    so it is treated as analytics metadata, never as an authorization input.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None