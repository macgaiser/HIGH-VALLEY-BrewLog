from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import get_current_user
from app.database import BACKGROUND_IMAGE_DIR, BORDER_GRAPHIC_DIR, LOGO_DIR, init_db
from app.routers import batches, inventory, settings, statistics

app = FastAPI(title="HighValley BrewLog")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/logos", StaticFiles(directory=LOGO_DIR), name="logos")
app.mount("/border-graphics", StaticFiles(directory=BORDER_GRAPHIC_DIR), name="border-graphics")
app.mount("/background-images", StaticFiles(directory=BACKGROUND_IMAGE_DIR), name="background-images")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/batches")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    # Muss unter "/" statt "/static/sw.js" ausgeliefert werden, damit der
    # Service Worker per Default-Scope die gesamte App steuern darf (der
    # Scope eines Service Workers ist sonst auf sein eigenes Verzeichnis
    # begrenzt) - fuer die PWA-Installierbarkeit auf iPhone/Android/
    # Windows/Mac erforderlich.
    return FileResponse("app/static/sw.js", media_type="application/javascript")


app.include_router(batches.router, dependencies=[Depends(get_current_user)])
app.include_router(inventory.router, dependencies=[Depends(get_current_user)])
app.include_router(statistics.router, dependencies=[Depends(get_current_user)])
app.include_router(settings.router, dependencies=[Depends(get_current_user)])
