from fastapi import APIRouter, Depends

from app.security import AuthUser, current_user
from app.services.mcp_gateway import external_mcp_gateway


router = APIRouter(prefix="/api/v1", tags=["integrations"])


@router.get("/integrations")
async def integrations(_: AuthUser = Depends(current_user)):
    """Return non-secret integration metadata for the authenticated console."""
    github = external_mcp_gateway.public_status()
    return {
        "internal_tools": {
            "mode": "direct_python",
            "tools": ["service_status", "deployments", "incidents", "tickets"],
        },
        "external_mcp": [github],
    }
