from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import game, decks, cards

app = FastAPI(title="cEDH Simulator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(game.router, prefix="/api/game", tags=["game"])
app.include_router(decks.router, prefix="/api/decks", tags=["decks"])
app.include_router(cards.router, prefix="/api/cards", tags=["cards"])


@app.get("/health")
def health():
    return {"status": "ok"}
