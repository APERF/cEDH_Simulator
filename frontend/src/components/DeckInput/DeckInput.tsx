import { useState } from "react";
import { validateDecklist } from "../../services/api";

interface Props {
  onConfirm: (name: string, decklist: string) => void;
}

export function DeckInput({ onConfirm }: Props) {
  const [name, setName] = useState("");
  const [decklist, setDecklist] = useState("");
  const [validation, setValidation] = useState<{
    valid: boolean;
    card_count: number;
    size_error: string | null;
    banned_cards: string[];
  } | null>(null);
  const [checking, setChecking] = useState(false);

  async function handleValidate() {
    setChecking(true);
    try {
      const result = await validateDecklist(name, decklist);
      setValidation(result);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="deck-input">
      <h2>Your Deck</h2>
      <input
        type="text"
        placeholder="Deck name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <textarea
        placeholder={"Paste decklist here (MTGO / Moxfield format):\n1 Sol Ring\n1 Command Tower\n..."}
        rows={20}
        value={decklist}
        onChange={(e) => setDecklist(e.target.value)}
      />
      <div className="actions">
        <button onClick={handleValidate} disabled={checking || !decklist}>
          {checking ? "Checking..." : "Validate Deck"}
        </button>
        {validation && (
          <div className={`validation ${validation.valid ? "valid" : "invalid"}`}>
            <p>{validation.card_count} cards</p>
            {validation.size_error && <p className="error">{validation.size_error}</p>}
            {validation.banned_cards.length > 0 && (
              <p className="error">Banned: {validation.banned_cards.join(", ")}</p>
            )}
            {validation.valid && (
              <button onClick={() => onConfirm(name, decklist)}>
                Confirm &amp; Continue
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
