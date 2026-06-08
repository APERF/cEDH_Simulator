from fastapi import APIRouter, HTTPException
from app.models.schemas import NewGameRequest, GameStateSchema

router = APIRouter()

# In-memory game sessions (replace with Redis/DB for persistence)
_sessions: dict[str, dict] = {}


@router.post("/new", response_model=dict)
async def new_game(request: NewGameRequest):
    """Start a new game session."""
    # TODO: parse user decklist, load 3 AI opponent decklists, build GameState
    return {"game_id": "placeholder", "message": "Game creation coming soon"}


@router.get("/{game_id}", response_model=dict)
async def get_game_state(game_id: str):
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    return _sessions[game_id]


@router.post("/{game_id}/action", response_model=dict)
async def player_action(game_id: str, action: dict):
    """Submit a player action (cast spell, activate ability, pass priority, etc.)."""
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    # TODO: route action to game engine
    return {"status": "ok", "log": []}


@router.post("/{game_id}/ai-turn", response_model=dict)
async def ai_turn(game_id: str):
    """Advance the current AI player's turn."""
    if game_id not in _sessions:
        raise HTTPException(status_code=404, detail="Game not found")
    # TODO: invoke active AI archetype
    return {"status": "ok", "log": []}
