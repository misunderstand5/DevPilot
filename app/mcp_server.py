from mcp.server import MCPServer

from app.services.tools import get_service_status, recent_deployments, open_incidents, open_tickets

mcp = MCPServer("DevPilot Ops Tools")


@mcp.tool()
async def service_status(service_name: str) -> dict:
    """查询一个服务的当前状态。只读。"""
    return await get_service_status(service_name)


@mcp.tool()
async def deployments(service_name: str, days: int = 7) -> list[dict]:
    """查询某服务最近若干天的部署记录。只读。"""
    return await recent_deployments(service_name, days)


@mcp.tool()
async def incidents(service_name: str | None = None) -> list[dict]:
    """查询未解决线上故障。只读。"""
    return await open_incidents(service_name)


@mcp.tool()
async def tickets(service_name: str | None = None) -> list[dict]:
    """查询未关闭工单。只读。"""
    return await open_tickets(service_name)


if __name__ == "__main__":
    mcp.run(transport="stdio")
