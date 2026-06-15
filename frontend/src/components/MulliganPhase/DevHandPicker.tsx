import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { devGetLibrary, devSetHand } from "../../services/api";
import type { GameState } from "../../types/game";

interface LibraryCard {
  id: string;
  name: string;
  type_line: string;
  mana_cost: string | null;
  image_uri: string | null;
}

interface Props {
  gameId: string;
  onConfirm: (newState: GameState) => void;
  onCancel: () => void;
}

interface HoveredCard {
  imageUri: string;
  rect: DOMRect;
}

function CardPreview({ imageUri, rect }: HoveredCard) {
  const previewWidth = 240;
  const previewHeight = 336;
  const margin = 12;

  let left = rect.left + rect.width / 2 - previewWidth / 2;
  left = Math.max(margin, Math.min(left, window.innerWidth - previewWidth - margin));

  const top =
    rect.top >= previewHeight + margin
      ? rect.top - previewHeight - margin
      : rect.bottom + margin;

  return createPortal(
    <img
      src={imageUri}
      style={{
        position: "fixed",
        left,
        top,
        width: previewWidth,
        height: previewHeight,
        borderRadius: 12,
        zIndex: 10000,
        pointerEvents: "none",
        boxShadow: "0 16px 48px rgba(0,0,0,0.9)",
        objectFit: "cover",
      }}
    />,
    document.body
  );
}

export function DevHandPicker({ gameId, onConfirm, onCancel }: Props) {
  const [cards, setCards] = useState<LibraryCard[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hovered, setHovered] = useState<HoveredCard | null>(null);

  useEffect(() => {
    devGetLibrary(gameId)
      .then((c) => setCards(c))
      .catch(() => setError("Failed to load library"))
      .finally(() => setLoading(false));
  }, [gameId]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 7) {
        next.add(id);
      }
      return next;
    });
  }

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const newState = await devSetHand(gameId, Array.from(selected));
      onConfirm(newState);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to set hand");
      setBusy(false);
    }
  }

  const filtered = cards.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="dev-picker-overlay">
      {hovered && <CardPreview {...hovered} />}
      <div className="dev-picker-panel">
        <div className="dev-picker-header">
          <div>
            <h2>Select Opening Hand</h2>
            <p className="dev-picker-sub">
              Dev tool — pick exactly 7 cards from your full decklist.
            </p>
          </div>
          <div className="dev-picker-count">
            <span className={selected.size === 7 ? "dev-picker-count--ready" : ""}>
              {selected.size} / 7
            </span>
          </div>
        </div>

        <input
          className="dev-picker-search"
          type="text"
          placeholder="Search by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />

        <div className="dev-picker-grid">
          {loading && <p className="dev-picker-empty">Loading decklist…</p>}
          {!loading && filtered.length === 0 && (
            <p className="dev-picker-empty">No cards match.</p>
          )}
          {filtered.map((card) => {
            const isSelected = selected.has(card.id);
            const isDisabled = !isSelected && selected.size >= 7;
            return (
              <div
                key={card.id}
                className={`dev-picker-card${isSelected ? " dev-picker-card--selected" : ""}${isDisabled ? " dev-picker-card--disabled" : ""}`}
                onClick={() => !isDisabled && toggle(card.id)}
                onMouseEnter={(e) => {
                  if (card.image_uri) {
                    setHovered({ imageUri: card.image_uri, rect: e.currentTarget.getBoundingClientRect() });
                  }
                }}
                onMouseLeave={() => setHovered(null)}
              >
                {card.image_uri ? (
                  <img src={card.image_uri} alt={card.name} className="dev-picker-card-img" />
                ) : (
                  <div className="dev-picker-card-text">
                    <span className="dev-picker-card-name">{card.name}</span>
                    <span className="dev-picker-card-type">{card.type_line}</span>
                  </div>
                )}
                {isSelected && <div className="dev-picker-check">✓</div>}
              </div>
            );
          })}
        </div>

        {error && <p className="dev-picker-error">{error}</p>}

        <div className="dev-picker-footer">
          <button onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            className="primary"
            onClick={confirm}
            disabled={busy || selected.size !== 7}
          >
            {busy ? "Setting hand…" : selected.size === 7 ? "Set Opening Hand" : `Select ${7 - selected.size} more…`}
          </button>
        </div>
      </div>
    </div>
  );
}
