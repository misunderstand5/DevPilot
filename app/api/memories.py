from fastapi import APIRouter, Depends, HTTPException

from app.security import AuthUser, current_user, require_permission
from app.services.long_term_memory import long_term_memory


router = APIRouter(prefix="/api/v1/memories", tags=["memories"])


@router.get("")
async def list_memories(user: AuthUser = Depends(current_user)):
    require_permission(user, "memory.own.read")
    return {"memories": await long_term_memory.list_for_user(user.tenant_id, user.id)}


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, user: AuthUser = Depends(current_user)):
    require_permission(user, "memory.own.delete")
    if not await long_term_memory.forget(memory_id, user.tenant_id, user.id):
        raise HTTPException(404, "memory not found")
    return {"deleted": True, "memory_id": memory_id}
