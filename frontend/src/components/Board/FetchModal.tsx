import { createPortal } from "react-dom";
import type { FetchOption } from "../../types/game";

interface Props {
  options: FetchOption[];
  onSelect: (cardId: string) => void;
  onClose: () => void;
}

export function FetchModal({ options, onSelect, onClose }: Props) {
  return createPortal(
    <div className="fetch-overlay" onClick={onClose}>
      <div className="fetch-modal" onClick={(e) => e.stopPropagation()}>
        <div className="fetch-header">
          <span className="fetch-title">Search your library</span>
          <button className="fetch-close" onClick={onClose}>✕</button>
        </div>

        {options.length === 0 ? (
          <div className="fetch-empty">
            <p>No valid targets in library.</p>
            <button className="primary" onClick={onClose}>Shuffle & Continue</button>
          </div>
        ) : (
          <div className="fetch-grid">
            {options.map((land) => (
              <div key={land.id} className="fetch-option" onClick={() => onSelect(land.id)}>
                {land.image_uri ? (
                  <img src={land.image_uri} alt={land.name} className="fetch-card-img" />
                ) : (
                  <div className="fetch-card-fallback">{land.name}</div>
                )}
                <div className="fetch-card-name">{land.name}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
