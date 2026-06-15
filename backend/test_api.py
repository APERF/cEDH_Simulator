import os, json
import anthropic

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
print(f"Key present: {bool(api_key)}, starts with: {api_key[:15]}...")

client = anthropic.Anthropic(api_key=api_key)
try:
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system='Reply with only this exact JSON array: [{"name":"test","skip":false,"effects":[]}]',
        messages=[{"role": "user", "content": "test card"}],
    )
    print("Raw response:", msg.content[0].text)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

from app.engine.effects.llm import parse_batch
test_cards = [
    {"name": "Dark Ritual", "type_line": "Instant", "oracle_text": "Add {B}{B}{B}."},
    {"name": "Wrath of God", "type_line": "Sorcery", "oracle_text": "Destroy all creatures. They cannot be regenerated."},
    {"name": "Lightning Bolt", "type_line": "Instant", "oracle_text": "Lightning Bolt deals 3 damage to any target."},
]
result = parse_batch(test_cards, api_key)
print("parse_batch result:", json.dumps(result, indent=2))
