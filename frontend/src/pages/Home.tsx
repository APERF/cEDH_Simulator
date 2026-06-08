import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listMetaDecks, createGame } from "../services/api";
import { DeckInput } from "../components/DeckInput/DeckInput";
import { useGameStore } from "../store/gameStore";
import type { MetaDeck } from "../types/game";

export function Home() {
  const [metaDecks, setMetaDecks] = useState<MetaDeck[]>([]);
  const [selectedOpponents, setSelectedOpponents] = useState<string[]>([]);
  const [playerDeck, setPlayerDeck] = useState<{ name: string; decklist: string } | null>(null);
  const { setGameId, setLoading, setError } = useGameStore();
  const navigate = useNavigate();

  useEffect(() => {
    listMetaDecks().then(setMetaDecks).catch(() => {});
  }, []);

  function toggleOpponent(commander: string) {
    setSelectedOpponents((prev) => {
      if (prev.includes(commander)) return prev.filter((c) => c !== commander);
      if (prev.length >= 3) return prev;
      return [...prev, commander];
    });
  }

  async function startGame() {
    if (!playerDeck || selectedOpponents.length !== 3) return;
    setLoading(true);
    try {
      const { game_id } = await createGame(
        playerDeck.name,
        playerDeck.decklist,
        selectedOpponents
      );
      setGameId(game_id);
      navigate(`/game/${game_id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="home">
      <h1>cEDH Simulator</h1>

      {!playerDeck ? (
        <DeckInput onConfirm={(name, decklist) => setPlayerDeck({ name, decklist })} />
      ) : (
        <div className="setup">
          <p>Deck ready: <strong>{playerDeck.name}</strong></p>

          <h2>Choose 3 AI Opponents ({selectedOpponents.length}/3)</h2>
          <div className="meta-deck-grid">
            {metaDecks.map((deck) => (
              <div
                key={deck.id}
                className={`meta-deck-card ${selectedOpponents.includes(deck.commander) ? "selected" : ""}`}
                onClick={() => toggleOpponent(deck.commander)}
              >
                <div className="commander">{deck.commander}</div>
                <div className="meta">{deck.archetype}</div>
                <div className="stats">
                  {deck.top_cuts} top cuts · {deck.conversion_rate}% conv.
                </div>
                <div className="colors">{deck.colors.join("")}</div>
              </div>
            ))}
          </div>

          <button
            onClick={startGame}
            disabled={selectedOpponents.length !== 3}
          >
            Start Game
          </button>
        </div>
      )}
    </div>
  );
}
