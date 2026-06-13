from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.player import Player
    from app.engine.card import Card

# Mana acceleration that counts as a "mana source" in hand evaluation
FAST_MANA_NAMES: frozenset[str] = frozenset({
    "sol ring", "mana crypt", "mana vault", "mox diamond", "chrome mox",
    "lotus petal", "jeweled lotus", "mox opal", "mox amber",
    "arcane signet", "felwar stone", "mind stone", "thought vessel",
    "talisman of dominance", "talisman of creativity", "talisman of conviction",
    "talisman of curiosity", "talisman of indulgence", "talisman of progress",
    "talisman of resilience", "talisman of unity",
    "dark ritual", "cabal ritual", "pyretic ritual", "desperate ritual",
    "birds of paradise", "noble hierarch", "llanowar elves", "fyndhorn elves",
    "elvish mystic", "avacyn's pilgrim", "deathrite shaman",
    "boreal druid", "elves of deep shadow",
})

# Cards so powerful that any hand with 2+ mana sources is an automatic keep
BROKEN_CARD_NAMES: frozenset[str] = frozenset({
    "mystic remora", "rhystic study", "esper sentinel",
    "necropotence", "ad nauseam", "thassa's oracle",
    "thoracle", "smothering tithe",
})

# Tutors count as a win path — they find whatever you need
TUTOR_NAMES: frozenset[str] = frozenset({
    "demonic tutor", "vampiric tutor", "imperial seal", "lim-dul's vault",
    "mystical tutor", "enlightened tutor", "worldly tutor", "gamble",
    "scheming symmetry", "dark petition", "diabolic intent", "grim tutor",
    "personal tutor", "merchant scroll", "whir of invention", "reshape",
    "fabricate", "intuition", "gifts ungiven", "spellseeker",
    "chord of calling", "finale of devastation", "eldritch evolution",
    "beseech the mirror", "beseech the queen", "rune-scarred demon",
    "long-term plans", "transmute artifact", "tainted pact",
})

# Cheap/free interaction worth noting in hand evaluation
INTERACTION_NAMES: frozenset[str] = frozenset({
    "force of will", "force of negation", "pact of negation",
    "fierce guardianship", "deflecting swat", "flusterstorm",
    "mental misstep", "swan song", "dispel", "negate", "counterspell",
    "mana drain", "arcane denial", "delay", "remand",
    "chain of vapor", "nature's claim", "abrupt decay", "assassin's trophy",
    "cyclonic rift", "winds of abandon", "swords to plowshares", "path to exile",
    "fatal push", "rapid hybridization", "pongify",
})

# Maximum mulligans the AI will take (stops at a 5-card effective hand)
MAX_MULLIGANS = 3
_MAX_MULLIGANS = MAX_MULLIGANS  # keep private alias for internal use


def _card_name(card: Card) -> str:
    return (card.name or "").lower().strip()


def _count_mana_sources(hand: list[Card]) -> int:
    return sum(
        1 for c in hand
        if c.is_land or _card_name(c) in FAST_MANA_NAMES
    )


def _count_fast_mana(hand: list[Card]) -> int:
    return sum(1 for c in hand if not c.is_land and _card_name(c) in FAST_MANA_NAMES)


def _has_broken_card(hand: list[Card]) -> bool:
    return any(_card_name(c) in BROKEN_CARD_NAMES for c in hand)


def _has_win_path(hand: list[Card]) -> bool:
    return any(_card_name(c) in TUTOR_NAMES for c in hand)


def _has_interaction(hand: list[Card]) -> bool:
    return any(_card_name(c) in INTERACTION_NAMES for c in hand)


def evaluate_hand(hand: list[Card], mulligan_count: int, seat: int) -> bool:
    """
    Return True if the AI should keep this hand.

    Priority order (from MAMTG / Sperling framework):
      1. Broken cards + any mana → automatic keep
      2. Good development + win path → keep
      3. Good development + interaction → keep (penalised for late seat on first look)
      4. Anything else → mulligan

    After 3 mulligans the standard drops: keep any hand with mana + anything.
    """
    mana_sources = _count_mana_sources(hand)

    # Hard floor: can't function without at least 2 mana sources
    if mana_sources < 2:
        return False

    # After 3 mulligans we're looking at a 5-card effective hand — keep anything functional
    if mulligan_count >= _MAX_MULLIGANS:
        return mana_sources >= 2 and (_has_win_path(hand) or _has_interaction(hand) or mana_sources >= 3)

    # Broken card + live mana = automatic keep regardless of everything else
    if _has_broken_card(hand):
        return True

    # "Good development": 3+ mana sources, or 2 with at least 1 fast-mana piece
    good_development = mana_sources >= 3 or (mana_sources >= 2 and _count_fast_mana(hand) >= 1)

    has_plan = _has_win_path(hand)
    has_interaction = _has_interaction(hand)

    # Solid development + win path: keep
    if good_development and has_plan:
        return True

    # Development + interaction: keep, but late seats are harder — mulligan on first look
    if good_development and has_interaction:
        if seat >= 3 and mulligan_count == 0:
            return False
        return True

    # Development alone with no plan: mulligan (interaction is a shared responsibility,
    # not a win condition — "you don't win in cEDH by not losing")
    return False


def choose_bottom_cards(hand: list[Card], count: int) -> list[str]:
    """
    Select the `count` worst cards to put on the bottom of library.
    Keeps mana sources, broken cards, tutors; bottoms high-CMC blanks first.
    """
    if count <= 0:
        return []

    def _priority(card: Card) -> float:
        name = _card_name(card)
        if card.is_land:
            return 0.0
        if name in FAST_MANA_NAMES:
            return 0.5
        if name in BROKEN_CARD_NAMES:
            return 0.5
        if name in TUTOR_NAMES:
            return 1.0
        if name in INTERACTION_NAMES:
            return 2.0
        # Non-essential spells: higher CMC = more likely to bottom
        return 3.0 + (card.cmc or 0)

    sorted_worst_first = sorted(hand, key=_priority, reverse=True)
    return [c.id for c in sorted_worst_first[:count]]


def run_ai_mulligan(player: Player, seat: int, game_log: list[str]) -> int:
    """
    Execute the full London-Mulligan sequence for an AI player.
    Logs each decision. Returns the number of mulligans taken.
    """
    mulligan_count = 0

    while mulligan_count < _MAX_MULLIGANS:
        if evaluate_hand(list(player.hand.cards), mulligan_count, seat):
            break
        # Return hand and draw 7 fresh cards
        player.return_hand_to_library()
        player.draw(7)
        mulligan_count += 1
        game_log.append(f"{player.name} mulligans ({mulligan_count})")

    # Determine how many cards must go to the bottom (first mulligan is free)
    cards_to_bottom = max(0, mulligan_count - 1)
    if cards_to_bottom > 0:
        bottom_ids = choose_bottom_cards(list(player.hand.cards), cards_to_bottom)
        player.put_on_bottom(bottom_ids)
        effective = 7 - cards_to_bottom
        game_log.append(f"{player.name} keeps {effective}, puts {cards_to_bottom} on bottom")
    else:
        if mulligan_count == 0:
            game_log.append(f"{player.name} keeps opening 7")
        else:
            game_log.append(f"{player.name} keeps 7 (free mulligan)")

    return mulligan_count
