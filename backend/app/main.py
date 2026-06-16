from dotenv import load_dotenv
load_dotenv()

import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import game, decks, cards
from app.api.routes import auth as auth_routes
from app.db.database import Base, engine, SessionLocal
from app.db.models import User
from app.auth.utils import hash_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cedh")

app = FastAPI(title="cEDH Simulator", version="0.1.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"→ {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"← {response.status_code} {request.url.path}")
        return response
    except Exception as exc:
        logger.error(f"✗ UNHANDLED {request.url.path}: {exc}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"detail": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(game.router, prefix="/api/game", tags=["game"])
app.include_router(decks.router, prefix="/api/decks", tags=["decks"])
app.include_router(cards.router, prefix="/api/cards", tags=["cards"])
app.include_router(auth_routes.router, prefix="/api/auth", tags=["auth"])


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    _seed_dev_user()


def _seed_dev_user():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "dev").first():
            db.add(User(
                username="dev",
                hashed_password=hash_password("dev"),
                role="dev",
            ))
            db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}
