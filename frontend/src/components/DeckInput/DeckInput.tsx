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

  async function handleAction() {
    if (validation?.valid) {
      onConfirm(name || "My Deck", decklist ?? input);
      return;
    }

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

  const buttonLabel =
    status === "importing" ? "Importing..." :
    status === "checking"  ? "Validating..." :
    validation?.valid      ? "Confirm Deck ✓" :
    isUrl                  ? "Import & Validate" :
    "Validate Deck";

  return (
    <div className="deck-input">
      <input
        type="text"
        placeholder="Deck name (auto-filled from Moxfield)"
        value={name}
        onChange={(e) => setName(e.target.value)}
        disabled={isUrl}
      />
      <textarea
        placeholder={"Paste a Moxfield URL:\n  https://www.moxfield.com/decks/...\n\nOr paste a decklist (MTGO format):\n  1 Sol Ring\n  1 Command Tower\n  ..."}
        rows={10}
        value={input}
        onChange={(e) => {
          setInput(e.target.value);
          setValidation(null);
          setImportError(null);
          setDecklist(null);
        }}
      />

      {isUrl && !importError && (
        <div className="url-hint">&#x2726; Moxfield URL detected — deck name will import from Moxfield. Click below to import &amp; validate</div>
      )}

      {importError && <div className="import-error">{importError}</div>}

      <button
        className={validation?.valid ? "primary" : ""}
        onClick={handleAction}
        disabled={busy || !input.trim()}
      >
        {buttonLabel}
      </button>

      {validation && (
        <div className={`validation-result ${validation.valid ? "valid" : "invalid"}`}>
          <div className="v-count">{validation.card_count} cards</div>
          {validation.size_error && <div className="v-error">{validation.size_error}</div>}
          {validation.banned_cards.length > 0 && (
            <div className="v-error">Banned: {validation.banned_cards.join(", ")}</div>
          )}
        </div>
      )}
    </div>
  );
}
