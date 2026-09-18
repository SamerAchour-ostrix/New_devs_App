import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from sqlalchemy import text
from app.core.auth import authenticate_request as get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/properties")
async def list_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="No tenant associated with this user",
        )
    
    from app.core.database_pool import db_pool
    
    try:
        async with db_pool.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT id, name
                    FROM properties
                    WHERE tenant_id = :tenant_id
                    ORDER BY name
                """),
                {"tenant_id": tenant_id},
            )
            rows = result.fetchall()
    except Exception:
        logger.exception("Property list unavailable for tenant %s", tenant_id)
        raise HTTPException(
            status_code=503,
            detail="Properties are temporarily unavailable",
        )
    
    items = [{"id": row.id, "name": row.name} for row in rows]
    
    return {"items": items, "total": len(items)}
