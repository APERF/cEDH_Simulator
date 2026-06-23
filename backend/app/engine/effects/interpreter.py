"""
Effect interpreter: executes LLM-generated effects_json specs against game state.

Two entry points:
  execute_spell(card, game_state, controller_id)
      — call from stack.py when an instant/sorcery resolves (spell_resolve trigger)
  json_to_card_effects(effects_json)
      — call from resolver.py to convert etb/upkeep/draw triggers into CardEffect objects
        for the normal trigger collection system
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.card import Card
    from app.engine.game_state import GameState


# ── Public entry points ───────────────────────────────────────────────────────

def execute_activated_ability(card: "Card", ability_spec: dict, game_state: "GameState", controller_id: str, target_ids: list | None = None) -> None:
    """Execute an activated ability that has resolved off the stack."""
    for action in ability_spec.get("actions", []):
        _run_action(action, game_state, controller_id, card)


def execute_spell(card: "Card", game_state: "GameState", controller_id: str) -> None:
    """Execute spell_resolve effects for a card that just resolved off the stack."""
    spec = getattr(card, "effects_json", None)
    if not spec or spec.get("skip"):
        return
    for effect in spec.get("effects", []):
        if effect.get("trigger") == "spell_resolve":
            _run_effect(effect, game_state, controller_id, card)


_TRIGGER_MAP: dict[str, str] = {
    "upkeep": "upkeep_begin",     # LLM shorthand → event constant
    "etb": "etb",
    "ltb": "ltb",
    "draw": "draw",
    "spell_cast": "spell_cast",
    "attacked": "attacked",
    "turn_begin": "turn_begin",
    "damage_dealt": "damage_dealt",
}


def json_to_card_effects(effects_json: dict) -> list:
    """
    Convert an effects_json dict into CardEffect objects for the trigger system.
    Only converts non-spell_resolve triggers (etb, upkeep_begin, draw, spell_cast, etc.).
    spell_resolve is handled directly in stack.py via execute_spell().
    """
    from app.engine.effects import CardEffect
    results = []
    for effect_spec in effects_json.get("effects", []):
        trigger_raw = effect_spec.get("trigger")
        if not trigger_raw or trigger_raw == "spell_resolve":
            continue
        trigger = _TRIGGER_MAP.get(trigger_raw, trigger_raw)
        spec = effect_spec  # capture for closure

        def _make_resolve(s: dict):
            def resolve(event, gs, card):
                if card is None:
                    return
                _run_effect(s, gs, card.controller_id, card)
            return resolve

        results.append(CardEffect(
            trigger=trigger,
            resolve=_make_resolve(spec),
            optional=effect_spec.get("optional", False),
            needs_choice=effect_spec.get("needs_choice", False),
            description=effect_spec.get("description", "Oracle text effect"),
        ))
    return results


# ── Internal execution ────────────────────────────────────────────────────────

def _run_effect(effect: dict, gs: "GameState", controller_id: str, card: "Card") -> None:
    for action in effect.get("actions", []):
        _run_action(action, gs, controller_id, card)


def _run_action(action: dict, gs: "GameState", controller_id: str, card: "Card") -> None:
    atype = action.get("type")
    player = gs.get_player(controller_id)
    card_name = getattr(card, "name", "Unknown") if card else "Unknown"

    if not player:
        return

    if atype == "add_mana":
        mana = action.get("mana", {})
        added = []
        for color, amount in mana.items():
            if amount and hasattr(player.mana_pool, color):
                setattr(player.mana_pool, color, getattr(player.mana_pool, color) + amount)
                added.append(f"{{{color}}}×{amount}")
        if added:
            gs.log(f"{card_name}: {player.name} adds {' '.join(added)}")

    elif atype == "draw":
        amount = action.get("amount", 1)
        who = action.get("who", "controller")
        targets = _resolve_who(who, gs, controller_id)
        for target in targets:
            drawn = target.draw(amount)
            gs.log(f"{card_name}: {target.name} draws {amount} card(s)")
            from app.engine.effects import GameEvent, EVENT_DRAW
            for _ in range(len(drawn)):
                gs.fire_event(GameEvent(type=EVENT_DRAW, controller_id=target.id))

    elif atype == "gain_life":
        amount = action.get("amount", 0)
        who = action.get("who", "controller")
        for target in _resolve_who(who, gs, controller_id):
            target.life_total += amount
            gs.log(f"{card_name}: {target.name} gains {amount} life")

    elif atype == "lose_life":
        amount = action.get("amount", 0)
        who = action.get("who", "each_opponent")
        for target in _resolve_who(who, gs, controller_id):
            target.life_total -= amount
            gs.log(f"{card_name}: {target.name} loses {amount} life")

    elif atype == "deal_damage":
        amount = action.get("amount", 0)
        to = action.get("to", "each_opponent")
        if to == "target":
            if player.is_human:
                target_type = action.get("target_type", "any")
                candidates: list[dict] = []
                for opp in gs.get_opponents(controller_id):
                    candidates.append({"id": opp.id, "name": opp.name, "controller_name": opp.name, "type": "player"})
                    for c in opp.battlefield.permanents:
                        if target_type == "any" or _matches_type_filter(c, target_type):
                            candidates.append({"id": c.id, "name": c.name, "controller_name": opp.name, "type": "permanent"})
                if candidates:
                    gs.pending_target_choice = {
                        "player_id": controller_id,
                        "card_name": card_name,
                        "action_type": "deal_damage",
                        "target_type": target_type,
                        "candidates": candidates,
                        "action_params": {"amount": amount},
                    }
                    gs.log(f"{card_name}: {player.name} must choose a target for {amount} damage")
                return
            targets_sorted = sorted(gs.get_opponents(controller_id), key=lambda p: p.life_total)
            if targets_sorted:
                targets_sorted[0].life_total -= amount
                gs.log(f"{card_name}: deals {amount} damage to {targets_sorted[0].name}")
        else:
            for target in _resolve_who(to, gs, controller_id):
                target.life_total -= amount
                gs.log(f"{card_name}: deals {amount} damage to {target.name}")

    elif atype == "destroy_all":
        _filter = action.get("filter", "creature")
        from app.models.schemas import Zone
        to_destroy = []
        for p in gs.players:
            for perm in list(p.battlefield.permanents):
                if _matches_type_filter(perm, _filter) and not perm.has_keyword("Indestructible"):
                    to_destroy.append((p, perm))
        for p, c in to_destroy:
            p.battlefield.remove(c.id)
            c.zone = Zone.GRAVEYARD
            p.graveyard.add(c)
        gs.log(f"{card_name}: destroys all {_filter}s ({len(to_destroy)} total)")

    elif atype == "exile_all":
        _filter = action.get("filter", "creature")
        from app.models.schemas import Zone
        to_exile = []
        for p in gs.players:
            for perm in list(p.battlefield.permanents):
                if _matches_type_filter(perm, _filter):
                    to_exile.append((p, perm))
        for p, c in to_exile:
            p.battlefield.remove(c.id)
            c.zone = Zone.EXILE
            p.exile.add(c)
        gs.log(f"{card_name}: exiles all {_filter}s ({len(to_exile)} total)")

    elif atype == "create_token":
        _create_tokens(gs, controller_id, action, card_name)

    elif atype == "untap_all":
        _filter = action.get("filter", "nonland_permanents")
        count = 0
        for perm in player.battlefield.permanents:
            if _filter == "nonland_permanents" and perm.is_land:
                continue
            if _filter == "creatures" and not perm.is_creature:
                continue
            if _filter == "artifacts" and not perm.is_artifact:
                continue
            if perm.tapped:
                perm.tapped = False
                count += 1
        gs.log(f"{card_name}: {player.name} untaps {count} {_filter}")

    elif atype == "discard":
        amount = action.get("amount", 1)
        who = action.get("who", "controller")
        from app.models.schemas import Zone
        for target in _resolve_who(who, gs, controller_id):
            for _ in range(min(amount, len(target.hand._cards))):
                # AI: discard lowest CMC; human: discard first (UI for choosing deferred)
                discarded = min(target.hand._cards, key=lambda c: c.cmc)
                target.hand._cards.remove(discarded)
                discarded.zone = Zone.GRAVEYARD
                target.graveyard.add(discarded)
                gs.log(f"{card_name}: {target.name} discards {discarded.name}")

    elif atype == "look_arrange":
        from app.models.schemas import Zone
        compute_expr = action.get("compute_amount")
        amount = _compute_amount(compute_expr, gs, controller_id, card) if compute_expr else action.get("amount", 1)
        keep_top = action.get("keep_top", 1)
        top_cards = list(player.library._cards)[:amount]
        if not top_cards:
            gs.log(f"{card_name}: {player.name} looks at top 0 cards (library empty)")
            return
        if player.is_human:
            gs.pending_look_arrange = {
                "player_id": controller_id,
                "card_name": card_name,
                "keep_top": keep_top,
                "cards": [{"id": c.id, "name": c.name, "image_uri": c.image_uri} for c in top_cards],
            }
            gs.log(f"{card_name}: {player.name} looks at top {len(top_cards)} card(s) — awaiting choice")
        else:
            looked = [player.library._cards.popleft() for _ in range(len(top_cards))]
            sorted_cards = sorted(looked, key=lambda c: c.cmc or 0, reverse=True)
            on_top = sorted_cards[:keep_top]
            on_bottom = sorted_cards[keep_top:]
            for c in on_bottom:
                player.library._cards.append(c)
            for c in reversed(on_top):
                player.library._cards.appendleft(c)
            gs.log(f"{card_name}: {player.name} arranges top {len(looked)} card(s), keeps {len(on_top)} on top")

    elif atype == "scry":
        amount = action.get("amount", 1)
        look = list(player.library._cards)[:amount]
        if not look:
            gs.log(f"{card_name}: {player.name} scrys {amount} (library empty)")
            return
        if player.is_human:
            gs.pending_look_arrange = {
                "player_id": controller_id,
                "card_name": card_name,
                "keep_top": amount,
                "scry_mode": True,
                "cards": [{"id": c.id, "name": c.name, "image_uri": c.image_uri} for c in look],
            }
            gs.log(f"{card_name}: {player.name} scrys {amount} — awaiting choice")
        else:
            peeked = [player.library._cards.popleft() for _ in range(len(look))]
            # keep high-CMC cards on top, bottom zero-value non-lands
            keep = [c for c in sorted(peeked, key=lambda c: c.cmc or 0, reverse=True) if c.cmc > 0 or c.is_land]
            bottom = [c for c in peeked if c not in keep]
            for c in bottom:
                player.library._cards.append(c)
            for c in reversed(keep):
                player.library._cards.appendleft(c)
            gs.log(f"{card_name}: {player.name} scrys {amount} ({len(keep)} kept on top, {len(bottom)} to bottom)")

    elif atype == "mill":
        amount = action.get("amount", 1)
        who = action.get("who", "controller")
        from app.models.schemas import Zone
        for target in _resolve_who(who, gs, controller_id):
            milled = 0
            for _ in range(amount):
                if target.library._cards:
                    c = target.library._cards.popleft()
                    c.zone = Zone.GRAVEYARD
                    target.graveyard.add(c)
                    milled += 1
            gs.log(f"{card_name}: {target.name} mills {milled} card(s)")

    elif atype == "search_library":
        _filter = action.get("filter", "any")
        destination = action.get("destination", "hand")
        from app.models.schemas import Zone
        candidates = [
            c for c in player.library._cards
            if _filter == "any" or _filter.lower() in c.type_line.lower()
        ]
        if candidates:
            chosen = max(candidates, key=lambda c: c.cmc)
            player.library._cards.remove(chosen)
            if destination == "hand":
                chosen.zone = Zone.HAND
                player.hand._cards.append(chosen)
                player.library.shuffle()
            elif destination == "top_of_library":
                # Shuffle first (implicit in searching), then place on top
                player.library.shuffle()
                player.library._cards.appendleft(chosen)
                chosen.zone = Zone.LIBRARY
            elif destination == "battlefield":
                chosen.zone = Zone.BATTLEFIELD
                player.battlefield.add(chosen)
                player.library.shuffle()
            gs.log(f"{card_name}: {player.name} searches for {chosen.name} → {destination}")

    elif atype == "put_on_top":
        amount = action.get("amount", 1)
        from app.models.schemas import Zone
        sorted_hand = sorted(player.hand._cards, key=lambda c: c.cmc or 0)
        put_back = sorted_hand[:min(amount, len(sorted_hand))]
        for c in put_back:
            player.hand._cards.remove(c)
            player.library._cards.appendleft(c)
            c.zone = Zone.LIBRARY
        gs.log(f"{card_name}: {player.name} puts {len(put_back)} card(s) on top of library")

    elif atype in ("destroy", "exile", "bounce"):
        if player.is_human:
            target_type = action.get("target_type", "permanent")
            candidates = []
            for opp in gs.get_opponents(controller_id):
                for c in opp.battlefield.permanents:
                    if _matches_type_filter(c, target_type):
                        candidates.append({"id": c.id, "name": c.name, "controller_name": opp.name, "type": "permanent"})
            if candidates:
                gs.pending_target_choice = {
                    "player_id": controller_id,
                    "card_name": card_name,
                    "action_type": atype,
                    "target_type": target_type,
                    "candidates": candidates,
                    "action_params": {},
                }
                gs.log(f"{card_name}: {player.name} must choose a target for {atype}")
            else:
                gs.log(f"{card_name}: no valid targets for {atype}")
        else:
            _auto_target_removal(atype, action, gs, controller_id, card_name)

    elif atype == "sacrifice":
        target_type = action.get("target_type", "permanent")
        who = action.get("who", "controller")
        from app.models.schemas import Zone
        for target in _resolve_who(who, gs, controller_id):
            candidates = [c for c in target.battlefield.permanents if _matches_type_filter(c, target_type)]
            if not candidates:
                gs.log(f"{card_name}: {target.name} has no {target_type} to sacrifice")
                continue
            if target.is_human:
                gs.pending_target_choice = {
                    "player_id": target.id,
                    "card_name": card_name,
                    "action_type": "sacrifice",
                    "target_type": target_type,
                    "candidates": [{"id": c.id, "name": c.name, "controller_name": target.name, "type": "permanent"} for c in candidates],
                    "action_params": {},
                }
                gs.log(f"{card_name}: {target.name} must sacrifice a {target_type}")
            else:
                victim = min(candidates, key=lambda c: c.cmc)
                target.battlefield.remove(victim.id)
                victim.zone = Zone.GRAVEYARD
                target.graveyard.add(victim)
                gs.log(f"{card_name}: {target.name} sacrifices {victim.name}")

    elif atype == "return_from_graveyard":
        filter_type = action.get("filter", "any")
        destination = action.get("destination", "hand")
        who = action.get("who", "controller")
        from app.models.schemas import Zone
        for target in _resolve_who(who, gs, controller_id):
            candidates = [
                c for c in target.graveyard._cards
                if filter_type == "any" or filter_type.lower() in (c.type_line or "").lower()
            ]
            if not candidates:
                gs.log(f"{card_name}: {target.name} has no {filter_type} in graveyard")
                continue
            chosen = max(candidates, key=lambda c: c.cmc)
            target.graveyard._cards.remove(chosen)
            if destination == "hand":
                chosen.zone = Zone.HAND
                target.hand._cards.append(chosen)
            elif destination == "battlefield":
                chosen.zone = Zone.BATTLEFIELD
                chosen.tapped = False
                target.battlefield.add(chosen)
            elif destination == "top_of_library":
                chosen.zone = Zone.LIBRARY
                target.library._cards.appendleft(chosen)
            gs.log(f"{card_name}: {target.name} returns {chosen.name} from graveyard to {destination}")

    elif atype == "add_counters":
        counter_type = action.get("counter_type", "+1/+1")
        amount = action.get("amount", 1)
        target_filter = action.get("target_filter", "self")
        filter_type = action.get("filter", "creature")
        who = action.get("who", "controller")
        if target_filter == "self":
            if card:
                card.counters[counter_type] = card.counters.get(counter_type, 0) + amount
                gs.log(f"{card_name}: gets {amount} {counter_type} counter(s) (total: {card.counters[counter_type]})")
        else:
            for target_player in _resolve_who(who, gs, controller_id):
                for perm in target_player.battlefield.permanents:
                    if _matches_type_filter(perm, filter_type):
                        perm.counters[counter_type] = perm.counters.get(counter_type, 0) + amount
                gs.log(f"{card_name}: {target_player.name}'s {filter_type}s get {amount} {counter_type} counter(s)")

    elif atype == "tap_target":
        target_type = action.get("target_type", "creature")
        who = action.get("who", "each_opponent")
        for target_player in _resolve_who(who, gs, controller_id):
            candidates = [c for c in target_player.battlefield.permanents if _matches_type_filter(c, target_type) and not c.tapped]
            if candidates:
                chosen = max(candidates, key=lambda c: c.cmc)
                chosen.tapped = True
                gs.log(f"{card_name}: taps {chosen.name}")

    elif atype == "tap_all":
        target_type = action.get("target_type", "creature")
        who = action.get("who", "each_opponent")
        count = 0
        for target_player in _resolve_who(who, gs, controller_id):
            for perm in target_player.battlefield.permanents:
                if _matches_type_filter(perm, target_type) and not perm.tapped:
                    perm.tapped = True
                    count += 1
        gs.log(f"{card_name}: taps {count} {target_type}(s)")

    elif atype == "counter_spell":
        if not gs.stack.is_empty:
            target = gs.stack.pop()
            if target:
                ctrl = gs.get_player(target.controller_id)
                if ctrl:
                    from app.models.schemas import Zone
                    target.card.zone = Zone.GRAVEYARD
                    ctrl.graveyard.add(target.card)
                gs.log(f"{card_name}: counters {target.card.name}")

    elif atype == "exile_library_until_named":
        if player.is_human:
            gs.pending_dc_name = {"player_id": controller_id, "spell_name": card_name}
            gs.log(f"{card_name}: waiting for {player.name} to name a card")
        else:
            _exile_library_for_name(gs, controller_id, "__nonexistent__", card_name)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _exile_library_for_name(gs: "GameState", player_id: str, named_card: str, spell_name: str) -> None:
    """Exile top N cards then reveal one by one until named card found or library exhausted."""
    from app.models.schemas import Zone
    player = gs.get_player(player_id)
    if not player:
        return
    named_lower = named_card.strip().lower()
    exiled_count = 0
    for _ in range(min(6, len(player.library._cards))):
        c = player.library._cards.popleft()
        c.zone = Zone.EXILE
        player.exile.add(c)
        exiled_count += 1
    found = None
    while player.library._cards:
        c = player.library._cards.popleft()
        if c.name.lower() == named_lower:
            found = c
            break
        c.zone = Zone.EXILE
        player.exile.add(c)
        exiled_count += 1
    if found:
        found.zone = Zone.HAND
        player.hand.add(found)
        gs.log(f"{spell_name}: {player.name} named '{named_card}' — found it, {exiled_count} cards exiled")
    else:
        gs.log(f"{spell_name}: {player.name} named '{named_card}' — not found, entire library exiled ({exiled_count} cards)")


def _resolve_who(who: str, gs: "GameState", controller_id: str) -> list:
    player = gs.get_player(controller_id)
    if who == "controller":
        return [player] if player else []
    if who in ("each_opponent", "all_opponents"):
        return gs.get_opponents(controller_id)
    if who == "each_player":
        return list(gs.players)
    if who == "target":
        # Caller should check needs_target before calling this
        return gs.get_opponents(controller_id)[:1]
    return [player] if player else []


def _matches_type_filter(perm, _filter: str) -> bool:
    f = _filter.lower()
    tl = perm.type_line.lower()
    if f == "creature":
        return perm.is_creature
    if f == "artifact":
        return perm.is_artifact
    if f == "enchantment":
        return perm.is_enchantment
    if f == "land":
        return perm.is_land
    if f == "permanent":
        return True
    return f in tl


def _compute_amount(expr: str, gs: "GameState", controller_id: str, card: "Card") -> int:
    """Resolve a dynamic compute_amount expression to an integer."""
    if not expr:
        return 0
    player = gs.get_player(controller_id)
    if not player:
        return 0
    source_id = getattr(card, "id", None)
    if expr.startswith("devotion:"):
        color = expr.split(":")[1].upper()
        return sum(
            (c.mana_cost or "").count(color)
            for c in player.battlefield.permanents
            if c.id != source_id
        )
    if expr == "opponent_count":
        return len(gs.get_opponents(controller_id))
    if expr == "hand_count":
        return len(player.hand._cards)
    if expr == "library_count":
        return len(player.library._cards)
    if expr == "creatures_count":
        return sum(1 for c in player.battlefield.permanents if c.is_creature)
    if expr == "artifacts_opponents":
        return sum(
            1 for opp in gs.get_opponents(controller_id)
            for c in opp.battlefield.permanents
            if c.is_artifact or c.is_enchantment
        )
    return 0


def _pay_ability_cost(card: "Card", cost: dict, gs: "GameState", controller_id: str) -> bool:
    """Pay an activated ability cost. Returns True if fully paid, False if not payable."""
    from app.models.schemas import Zone
    player = gs.get_player(controller_id)
    if not player:
        return False
    if cost.get("tap"):
        if card.tapped:
            return False
        card.tapped = True
    mana_str = cost.get("mana")
    if mana_str:
        from app.engine.mana_cost import parse_cost, can_pay, pay as pay_mana
        parsed = parse_cost(mana_str)
        if not can_pay(player.mana_pool, parsed):
            return False
        pay_mana(player.mana_pool, parsed)
    pay_life = cost.get("pay_life", 0)
    if pay_life:
        if player.life_total <= pay_life:
            return False
        player.life_total -= pay_life
    discard_count = cost.get("discard", 0)
    if discard_count:
        if len(player.hand._cards) < discard_count:
            return False
        for _ in range(discard_count):
            c = player.hand._cards.pop()
            c.zone = Zone.GRAVEYARD
            player.graveyard.add(c)
    if cost.get("sacrifice_self"):
        if card.zone != Zone.BATTLEFIELD:
            return False
        ctrl = gs.get_player(card.controller_id)
        if ctrl:
            ctrl.battlefield.remove(card.id)
            card.zone = Zone.GRAVEYARD
            ctrl.graveyard.add(card)
    return True


def _create_tokens(gs: "GameState", controller_id: str, action: dict, card_name: str) -> None:
    import uuid
    from app.engine.card import Card
    from app.models.schemas import Zone
    player = gs.get_player(controller_id)
    if not player:
        return
    compute_expr = action.get("compute_count")
    count = _compute_amount(compute_expr, gs, controller_id, None) if compute_expr else action.get("count", 1)
    token_name = action.get("token_name", "Token")
    power = action.get("power", "1")
    toughness = action.get("toughness", "1")
    token_type = action.get("token_type", "Artifact — Token")
    oracle = action.get("oracle_text", "")
    for _ in range(count):
        token = Card(
            id=str(uuid.uuid4()),
            name=token_name,
            mana_cost="",
            cmc=0,
            type_line=token_type,
            oracle_text=oracle,
            colors=[],
            color_identity=[],
            keywords=[],
            owner_id=controller_id,
            controller_id=controller_id,
            zone=Zone.BATTLEFIELD,
        )
        player.battlefield.add(token)
    gs.log(f"{card_name}: {player.name} creates {count} {token_name} token(s)")


def _auto_target_removal(atype: str, action: dict, gs: "GameState", controller_id: str, card_name: str) -> None:
    """AI auto-targeting for destroy/exile/bounce effects."""
    from app.models.schemas import Zone
    target_type = action.get("target_type", "creature")
    for opp in gs.get_opponents(controller_id):
        candidates = [
            c for c in opp.battlefield.permanents
            if _matches_type_filter(c, target_type)
        ]
        if not candidates:
            continue
        # Target the highest-CMC permanent (most threatening)
        target = max(candidates, key=lambda c: c.cmc)
        if atype == "destroy" and not target.has_keyword("Indestructible"):
            opp.battlefield.remove(target.id)
            target.zone = Zone.GRAVEYARD
            opp.graveyard.add(target)
            gs.log(f"{card_name}: destroys {target.name}")
        elif atype == "exile":
            opp.battlefield.remove(target.id)
            target.zone = Zone.EXILE
            opp.exile.add(target)
            gs.log(f"{card_name}: exiles {target.name}")
        elif atype == "bounce":
            opp.battlefield.remove(target.id)
            target.zone = Zone.HAND
            opp.hand._cards.append(target)
            gs.log(f"{card_name}: bounces {target.name} to hand")
        return
