from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import game, decks, cards
from app.api.routes import auth as auth_routes
from app.db.database import Base, engine, SessionLocal
from app.db.models import User
from app.auth.utils import hash_password

app = FastAPI(title="cEDH Simulator", version="0.1.0")

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
