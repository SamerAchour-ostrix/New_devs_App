import logging
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from typing import Dict, Any, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "UTC"


async def _get_property_timezone(session, property_id: str, tenant_id: str) -> str:
    """Returns the IANA timezone a property reports its calendar in."""
    result = await session.execute(
        text("""
            SELECT timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()

    if row is None or not row.timezone:
        logger.warning(
            "No timezone for property %s (tenant: %s), assuming %s",
            property_id, tenant_id, DEFAULT_TIMEZONE,
        )
        return DEFAULT_TIMEZONE
    return row.timezone


def _month_bounds_utc(month: int, year: int, tz_name: str) -> Tuple[datetime, datetime]:
    """Returns the half-open [start, end) UTC range covering a local calendar month."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown timezone %r, falling back to %s", tz_name, DEFAULT_TIMEZONE)
        tz = ZoneInfo(DEFAULT_TIMEZONE)

    start_local = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_local = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_local = datetime(year + 1, 1, 1, tzinfo=tz)

    return start_local.astimezone(dt_timezone.utc), end_local.astimezone(dt_timezone.utc)


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month, in the property's local calendar.
    """
    from app.core.database_pool import db_pool

    try:
        async with db_pool.get_session() as session:
            tz_name = await _get_property_timezone(session, property_id, tenant_id)
            start_utc, end_utc = _month_bounds_utc(month, year, tz_name)

            result = await session.execute(
                text("""
                    SELECT COALESCE(SUM(total_amount), 0) AS total
                    FROM reservations
                    WHERE property_id = :property_id
                      AND tenant_id = :tenant_id
                      AND check_in_date >= :start_utc
                      AND check_in_date < :end_utc
                """),
                {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                },
            )
            row = result.fetchone()
    except Exception:
        logger.exception(
            "Monthly revenue query failed for %s (tenant: %s) %04d-%02d",
            property_id, tenant_id, year, month,
        )
        raise

    return Decimal(str(row.total))


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    from app.core.database_pool import db_pool

    query = text("""
        SELECT 
            property_id,
            SUM(total_amount) as total_revenue,
            COUNT(*) as reservation_count
        FROM reservations 
        WHERE property_id = :property_id AND tenant_id = :tenant_id
        GROUP BY property_id
    """)

    try:
        async with db_pool.get_session() as session:
            result = await session.execute(query, {
                "property_id": property_id,
                "tenant_id": tenant_id
            })
            row = result.fetchone()
    except Exception:
        logger.exception(
            "Revenue query failed for %s (tenant: %s)", property_id, tenant_id
        )
        raise

    if row is None:
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0
        }

    total_revenue = Decimal(str(row.total_revenue))
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(total_revenue),
        "currency": "USD",
        "count": row.reservation_count
    }
