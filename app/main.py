from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings

app = FastAPI(
    title="AI Innovation Hub API",
    description=(
        "Collaborative internal platform for centralizing, tracking and developing AI initiatives "
        "at Onfly. Users propose ideas, developers collaborate and implement them, and admins "
        "manage the pipeline through a role-based dashboard.\n\n"
        "**Roles:**\n"
        "- `user` – propose ideas, vote, comment\n"
        "- `developer` – everything a user can do + join ideas as collaborator, update status\n"
        "- `admin` – platform management dashboard, user role management (read-only for ideas)\n\n"
        "**Authentication:** Bearer JWT. Obtain a token via `POST /api/auth/login` or "
        "`POST /api/auth/register`, then pass it as `Authorization: Bearer <token>`."
    ),
    version="1.0.0",
    docs_url=None,    # disabled — served manually below with local assets
    redoc_url=None,   # disabled — served manually below with local assets
    openapi_tags=[
        {"name": "Auth", "description": "Registration, login, and current user endpoints."},
        {"name": "Ideas", "description": "Create, list, update and delete AI initiative ideas."},
        {"name": "Votes", "description": "Toggle vote on an idea to express support (user and developer only)."},
        {"name": "Collaborators", "description": "Join or leave an idea as a developer collaborator."},
        {"name": "Comments", "description": "Add and list comments on ideas."},
        {"name": "AI", "description": "Auto-categorization and similar ideas via HuggingFace Inference API."},
        {"name": "Admin", "description": "Admin-only endpoints: user management and platform stats."},
        {"name": "Ranking", "description": "Developer leaderboard ranked by completed idea collaborations."},
        {"name": "Health", "description": "API health check."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"], summary="API health check")
async def health_check():
    """Returns the current health status of the API."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Serve Swagger UI assets locally (no external CDN — works offline)
# ---------------------------------------------------------------------------
try:
    from swagger_ui_bundle import swagger_ui_path
    app.mount("/swagger-static", StaticFiles(directory=swagger_ui_path), name="swagger-static")
    _SWAGGER_JS = "/swagger-static/swagger-ui-bundle.js"
    _SWAGGER_CSS = "/swagger-static/swagger-ui.css"
except ImportError:
    # Fallback to CDN if package not installed
    _SWAGGER_JS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
    _SWAGGER_CSS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"


@app.get("/docs", include_in_schema=False)
async def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="AI Innovation Hub API — Docs",
        swagger_js_url=_SWAGGER_JS,
        swagger_css_url=_SWAGGER_CSS,
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_ui() -> HTMLResponse:
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="AI Innovation Hub API — ReDoc",
    )


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------
from app.routers.auth import router as auth_router  # noqa: E402
from app.routers.admin import router as admin_router  # noqa: E402
from app.routers.ideas import router as ideas_router  # noqa: E402
from app.routers.votes import router as votes_router  # noqa: E402
from app.routers.collaborators import router as collaborators_router  # noqa: E402
from app.routers.comments import router as comments_router  # noqa: E402
from app.routers.ai import router as ai_router  # noqa: E402
from app.routers.ranking import router as ranking_router  # noqa: E402

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(ideas_router)
app.include_router(votes_router)
app.include_router(collaborators_router)
app.include_router(comments_router)
app.include_router(ai_router)
app.include_router(ranking_router)


# ---------------------------------------------------------------------------
# Force OpenAPI 3.0.2 — swagger-ui 4.x bundled locally doesn't support 3.1.0
# ---------------------------------------------------------------------------
def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    app.openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version="3.0.2",
        description=app.description,
        tags=app.openapi_tags,
        routes=app.routes,
    )
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]
