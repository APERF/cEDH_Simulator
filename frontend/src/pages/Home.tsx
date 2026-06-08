import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listMetaDecks, createGame } from "../services/api";
import { DeckInput } from "../components/DeckInput/DeckInput";
import { useGameStore } from "../store/gameStore";
import type { MetaDeck } from "../types/game";

const PIP_ORDER = ["W", "U", "B", "R", "G", "C"] as const;

function ColorPips({ colors }: { colors: string[] }) {
  const ordered = PIP_ORDER.filter((c) => colors.includes(c));
  if (!ordered.length) return null;
  return (
    <div className="color-pips">
      {ordered.map((c) => <span key={c} className={`pip pip-${c}`} />)}
    </div>
  );
}

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
      const { game_id } = await createGame(playerDeck.name, playerDeck.decklist, selectedOpponents);
      setGameId(game_id);
      navigate(`/game/${game_id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const ready = !!playerDeck && selectedOpponents.length === 3;
  const remaining = 3 - selectedOpponents.length;

  return (
    <div className="home">
      <div className="home-hero">
        <h1>cEDH Simulator</h1>
        <p>Competitive Commander — test your lines against top meta AI opponents</p>
      </div>

      <div className="setup-grid">
        {/* Step 1 — Your Deck */}
        <div className="setup-panel">
          <div className="panel-title">
            <span className="step-badge">1</span>
            <span className="panel-title-text">Your Deck</span>
          </div>

          {playerDeck ? (
            <div className="deck-confirmed">
              <div className="deck-confirmed-info">
                <div className="dc-name">{playerDeck.name}</div>
                <div className="dc-sub">100 cards · validated</div>
              </div>
              <button onClick={() => setPlayerDeck(null)}>Change</button>
            </div>
          ) : (
            <DeckInput onConfirm={(name, decklist) => setPlayerDeck({ name, decklist })} />
          )}
        </div>

        {/* Step 2 — Choose Opponents */}
        <div className="setup-panel">
          <div className="panel-title">
            <span className="step-badge">2</span>
            <span className="panel-title-text">Choose 3 AI Opponents</span>
            <span className="opponent-count-badge">{selectedOpponents.length} / 3</span>
          </div>

          <div className="meta-deck-grid">
            {metaDecks.map((deck) => (
              <div
                key={deck.id}
                className={`meta-deck-card ${selectedOpponents.includes(deck.commander) ? "selected" : ""}`}
                onClick={() => toggleOpponent(deck.commander)}
              >
                <ColorPips colors={deck.colors} />
                <div className="dc-commander">{deck.commander}</div>
                <div className="dc-archetype">{deck.archetype}</div>
                <div className="dc-stats">{deck.top_cuts} cuts · {deck.conversion_rate}%</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Start bar */}
      <div className="start-bar">
        <div className="start-status">
          {!playerDeck && <span>Import or paste your deck to get started</span>}
          {playerDeck && !ready && (
            <span>
              <strong>{playerDeck.name}</strong> — select {remaining} more opponent{remaining !== 1 ? "s" : ""}
            </span>
          )}
          {ready && (
            <span>
              <strong>{playerDeck!.name}</strong> vs {selectedOpponents.join(", ")}
            </span>
          )}
        </div>
        <button className="primary" onClick={startGame} disabled={!ready}>
          Start Game →
        </button>
      </div>
    </div>
  );
}
