from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
import asyncio

from providers.mcp_summaries_provider import McpSummariesProvider
from integrations.google_sheets import upsert_summaries, read_all_summaries


app = FastAPI(title="Email Assistant Dashboard")

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

app.mount("/static", StaticFiles(directory="static"), name="static")


ROLE_TO_CLASS = {
    "Student": "tag-student",
    "Faculty": "tag-faculty",
    "Vendor": "tag-vendor",
}


class TimeoutError(Exception):
    pass


async def fetch_summaries_with_timeout(provider, limit: int, timeout_s: int = 30):
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, provider.get_summaries, limit), timeout=timeout_s)
    except asyncio.TimeoutError as e:
        raise TimeoutError("Summarization provider timed out") from e


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, limit: int = 20):
    """Dashboard loads from Google Sheets (our database)."""
    try:
        items = read_all_summaries()[:limit]
        # Attach role class
        for it in items:
            it["role_class"] = ROLE_TO_CLASS.get(it.get("role"), "tag-default")
    except Exception as e:
        print(f"Error reading from Sheets: {e}")
        items = []

    template = env.get_template("dashboard.html")
    html = template.render(items=items)
    return HTMLResponse(content=html)


@app.post("/sync-from-mcp")
async def sync_from_mcp(limit: int = 50, sheet_name: str = "EmailAssistantSummaries"):
    """Sync fresh data from MCP to Google Sheets (our database)."""
    provider = McpSummariesProvider()
    try:
        items = await fetch_summaries_with_timeout(provider, limit=limit, timeout_s=30)
    except TimeoutError:
        return JSONResponse({"ok": False, "error": "timeout"}, status_code=504)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    upsert_summaries(items, sheet_name=sheet_name)
    return {"ok": True, "count": len(items), "message": f"Synced {len(items)} contacts to Sheets"}


@app.get("/api/summaries")
async def api_summaries(limit: int = 20, source: str = "sheets"):
    """
    Get summaries. source='sheets' reads from database, source='mcp' fetches fresh from MCP.
    """
    if source == "mcp":
        provider = McpSummariesProvider()
        try:
            items = await fetch_summaries_with_timeout(provider, limit=limit, timeout_s=30)
        except TimeoutError:
            return JSONResponse({"ok": False, "error": "timeout"}, status_code=504)
    else:
        items = read_all_summaries()[:limit]
    
    for it in items:
        it["role_class"] = ROLE_TO_CLASS.get(it.get("role"), "tag-default")
    return {"ok": True, "count": len(items), "items": items, "source": source}


