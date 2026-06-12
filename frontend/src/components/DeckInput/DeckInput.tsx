import { useState, useEffect } from "react";
import { validateDecklist, fetchMoxfieldDeck, fetchEdhtop16Deck, listMetaDecks } from "../../services/api";
import type { MetaDeck } from "../../types/game";

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

interface Props {
  onConfirm: (name: string, decklist: string) => void;
}

function isMoxfieldUrl(value: string) {
  return /moxfield\.com\/decks\/[A-Za-z0-9_-]+/.test(value.trim());
}

export function DeckInput({ onConfirm }: Props) {
  const [mode, setMode] = useState<"paste" | "meta">("paste");
  const [metaDecks, setMetaDecks] = useState<MetaDeck[]>([]);
  const [loadingCommander, setLoadingCommander] = useState<string | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);

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

  useEffect(() => {
    if (mode === "meta" && metaDecks.length === 0) {
      listMetaDecks().then(setMetaDecks).catch(() => {});
    }
  }, [mode, metaDecks.length]);

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

  async function handleMetaPick(commander: string) {
    if (loadingCommander) return;
    setLoadingCommander(commander);
    setMetaError(null);
    try {
      const result = await fetchEdhtop16Deck(commander);
      const v = await validateDecklist(result.name, result.decklist);
      if (v.valid) {
        onConfirm(result.name, result.decklist);
      } else {
        setMetaError(
          `Imported but failed validation: ${v.size_error ?? v.banned_cards.join(", ")}`
        );
      }
    } catch (e: any) {
      setMetaError(
        e?.response?.data?.detail ?? "No public decklist found for this commander"
      );
    } finally {
      setLoadingCommander(null);
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
      <div className="di-tabs">
        <button
          className={`di-tab${mode === "paste" ? " active" : ""}`}
          onClick={() => setMode("paste")}
        >
          Paste / Import
        </button>
        <button
          className={`di-tab${mode === "meta" ? " active" : ""}`}
          onClick={() => setMode("meta")}
        >
          Browse Meta
        </button>
      </div>

      {mode === "paste" ? (
        <>
          <input
            type="text"
            placeholder="Deck name (auto-filled from Moxfield)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={isUrl}
          />
          <textarea
            placeholder={"Paste a Moxfield URL:\n  https://www.moxfield.com/decks/...\n\nOr paste a decklist (MTGO format):\n  1 Sol Ring\n  1 Command Tower\n  ..."}
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
        </>
      ) : (
        <>
          <p className="di-meta-hint">
            Top-performing decklists · 6-month window · 50+ player events · top 16 finish
          </p>
          {metaError && <div className="import-error">{metaError}</div>}
          <div className="meta-deck-grid di-meta-grid">
            {[...metaDecks].sort((a, b) => b.top_cuts - a.top_cuts).map((deck) => (
              <div
                key={deck.id}
                className={`meta-deck-card${loadingCommander === deck.commander ? " loading" : ""}${loadingCommander && loadingCommander !== deck.commander ? " dimmed" : ""}`}
                onClick={() => handleMetaPick(deck.commander)}
              >
                <ColorPips colors={deck.colors} />
                <div className="dc-commander">{deck.commander}</div>
                <div className="dc-archetype">{deck.archetype}</div>
                <div className="dc-stats">
                  {loadingCommander === deck.commander
                    ? "Fetching..."
                    : `${deck.top_cuts} cuts · ${deck.conversion_rate}%`}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
