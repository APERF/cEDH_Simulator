import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app.db.database import SessionLocal
from app.db.models import CardData

names = ["Demonic Consultation", "Thassa's Oracle", "Tainted Pact"]
with SessionLocal() as s:
    for name in names:
        card = s.query(CardData).filter(CardData.name == name).first()
        if card:
            print(f"=== {name} ===")
            print(f"oracle_text: {card.oracle_text}")
            print(f"effects_json:\n{json.dumps(card.effects_json, indent=2)}")
            print()
        else:
            print(f"{name}: NOT IN DB\n")
