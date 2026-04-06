"""Example: per-tool rate limits for expensive operations."""

from fastmcp import FastMCP
from fastmcp_guard import Guard
from fastmcp_guard.rate import RateLimit, rate_limit

mcp = FastMCP("rate-limited-server")

guard = Guard(
    mcp,
    rate_limit=RateLimit(per_key="200/minute"),  # base limit for all tools
)


@mcp.tool
def get_data(query: str) -> str:
    """Fast lookup — inherits the base 200/minute limit."""
    return f"Data: {query}"


@mcp.tool
@rate_limit("5/minute")  # much tighter — this tool is expensive
def run_analysis(dataset: str) -> dict:
    """Expensive ML analysis — limited to 5 calls/minute per key."""
    return {"result": "...", "dataset": dataset}


@mcp.tool
@rate_limit("1/hour")  # near-exclusive access
def retrain_model(config: dict) -> str:
    """Trigger model retraining — max 1/hour per key."""
    return "Retraining started"
