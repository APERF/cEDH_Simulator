import { useState } from "react";
import { validateDecklist, fetchMoxfieldDeck } from "../../services/api";

interface Props {
  onConfirm: (name: string, decklist: string) => void;
}

function isMoxfieldUrl(value: string) {
  return /moxfield\.com\/decks\/[A-Za-z0-9_-]+/.test(value.trim());
}

export function DeckInput({ onConfirm }: Props) {
  const [name, setName] = useState("");
  const [input, setInput] = useState("");
  const [decklist, setDecklist] = useState<string | null>(null);
  const [validation, setValidation] = useState<{
    valid: boolean;
    card_count: number;
    size_error: string | null;
    banned_cards: string[];
  } | null>(null);
  const [status, setStatus] = useState<"idle" | "importing" | "checking">("idle");
  const [importError, setImportError] = useState<string | null>(null);

  const isUrl = isMoxfieldUrl(input);
  const busy = status !== "idle";

  async function handleValidate() {
    setValidation(null);
    setImportError(null);

    let rawDecklist = input;
    let resolvedName = name;

    if (isUrl) {
      setStatus("importing");
      try {
        const result = await fetchMoxfieldDeck(input.trim());
        rawDecklist = result.decklist;
        setDecklist(rawDecklist);
        if (!resolvedName) {
          resolvedName = result.name;
          setName(result.name);
        }
      } catch (e: any) {
        setImportError(e?.response?.data?.detail ?? "Failed to import from Moxfield");
        setStatus("idle");
        return;
      }
    } else {
      setDecklist(input);
    }

    setStatus("checking");
    try {
      const result = await validateDecklist(resolvedName || "My Deck", rawDecklist);
      setValidation(result);
    } finally {
      setStatus("idle");
    }
  }

  function handleConfirm() {
    onConfirm(name || "My Deck", decklist ?? input);
  }

  return (
    <div className="deck-input">
      <h2>Your Deck</h2>
      <input
        type="text"
        placeholder="Deck name (optional — auto-filled from Moxfield)"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <textarea
        placeholder={
          "Paste a Moxfield URL:\n  https://www.moxfield.com/decks/...\n\nOr paste a decklist (MTGO / Moxfield format):\n  1 Sol Ring\n  1 Command Tower\n  ..."
        }
        rows={12}
        value={input}
        onChange={(e) => {
          setInput(e.target.value);
          setValidation(null);
          setImportError(null);
          setDecklist(null);
        }}
      />

      {isUrl && (
        <div className="url-hint">
          Moxfield URL detected — click below to import &amp; validate.
        </div>
      )}

      {importError && <div className="import-error">{importError}</div>}

      <div className="actions">
        <button onClick={handleValidate} disabled={busy || !input.trim()}>
          {status === "importing"
            ? "Importing..."
            : status === "checking"
            ? "Validating..."
            : isUrl
            ? "Import & Validate"
            : "Validate Deck"}
        </button>

        {validation && (
          <div className={`validation ${validation.valid ? "valid" : "invalid"}`}>
            <p>{validation.card_count} cards</p>
            {validation.size_error && (
              <p className="error">{validation.size_error}</p>
            )}
            {validation.banned_cards.length > 0 && (
              <p className="error">Banned: {validation.banned_cards.join(", ")}</p>
            )}
            {validation.valid && (
              <button onClick={handleConfirm}>Confirm &amp; Continue</button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
