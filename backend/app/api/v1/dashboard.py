import logging
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

CENTS = Decimal("0.01")

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Revenue summary unavailable for %s (tenant: %s)", property_id, tenant_id
        )
        raise HTTPException(
            status_code=503,
            detail="Revenue data is temporarily unavailable",
        )
    
    total_revenue = Decimal(revenue_data['total']).quantize(CENTS, rounding=ROUND_HALF_UP)
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": str(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
