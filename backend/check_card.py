import sys, os
wt = r"C:\Users\BanditCoot\Documents\ClaudeCodeProjects\cEDH_Simulator\.claude\worktrees\agent-a20ea75ccab055a17\backend"
sys.path.insert(0, wt)
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cedh_simulator")
from app.engine.effects.registry import REGISTRY, SPELL_REGISTRY
print(f"Registry: {len(REGISTRY)} cards")
print(f"Spell registry: {len(SPELL_REGISTRY)} spells")
print("Spell keys:", list(SPELL_REGISTRY.keys()))
print("\nSample registry keys:", sorted(REGISTRY.keys())[:10])
