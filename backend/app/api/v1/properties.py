from fastapi import APIRouter, Depends
from typing import Dict, Any, List
from app.core.auth import authenticate_request as get_current_user
from app.core.database_pool import DatabasePool

router = APIRouter()


@router.get("/properties")
async def list_properties(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """List properties belonging to the current user's tenant only."""
    tenant_id = getattr(current_user, "tenant_id", None)

    if not tenant_id:
        return {"properties": []}

    from sqlalchemy import text

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        return {"properties": []}

    async with db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT id, name FROM properties WHERE tenant_id = :tenant_id ORDER BY id"),
            {"tenant_id": tenant_id},
        )
        rows = result.fetchall()

    properties: List[Dict[str, str]] = [{"id": row.id, "name": row.name} for row in rows]
    return {"properties": properties}
