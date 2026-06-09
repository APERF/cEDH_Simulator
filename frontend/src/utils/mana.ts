import type { ManaPool } from "../types/game";

const ALL_COLORS = ["W", "U", "B", "R", "G", "C"] as const;
type Color = (typeof ALL_COLORS)[number];

function clonePool(pool: ManaPool): Record<Color, number> {
  return { W: pool.W, U: pool.U, B: pool.B, R: pool.R, G: pool.G, C: pool.C };
}

/**
 * Returns true if the mana pool can pay the given Scryfall mana cost string,
 * plus any extra generic mana (e.g. commander tax).
 */
export function canAfford(manaCost: string | null, pool: ManaPool | undefined, extraGeneric = 0): boolean {
  if (!pool) return true;  // pool not yet loaded — optimistically allow
  const cost = manaCost ?? "";
  if (!cost && extraGeneric === 0) return true;

  const avail = clonePool(pool);

  // Specific colors: {W} {U} {B} {R} {G}
  for (const color of ["W", "U", "B", "R", "G"] as const) {
    const count = (cost.match(new RegExp(`\\{${color}\\}`, "g")) ?? []).length;
    if (avail[color] < count) return false;
    avail[color] -= count;
  }

  // True colorless: {C}
  const cCount = (cost.match(/\{C\}/g) ?? []).length;
  if (avail.C < cCount) return false;
  avail.C -= cCount;

  // Hybrid: {W/U} etc. — greedy: use richer of the pair
  for (const m of cost.matchAll(/\{([WUBRG])\/([WUBRG])\}/g)) {
    const c1 = m[1] as Color;
    const c2 = m[2] as Color;
    if (avail[c1] > 0 && avail[c1] >= avail[c2]) {
      avail[c1]--;
    } else if (avail[c2] > 0) {
      avail[c2]--;
    } else {
      const total = ALL_COLORS.reduce((s, c) => s + avail[c], 0);
      if (total <= 0) return false;
      const best = ALL_COLORS.reduce((a, b) => (avail[a] >= avail[b] ? a : b));
      avail[best]--;
    }
  }

  // Generic: {1} {2} etc.
  let generic = extraGeneric;
  for (const m of cost.matchAll(/\{(\d+)\}/g)) {
    generic += parseInt(m[1]);
  }

  const totalLeft = ALL_COLORS.reduce((s, c) => s + avail[c], 0);
  return totalLeft >= generic;
}

/** Total mana in the pool across all colors. */
export function poolTotal(pool: ManaPool): number {
  return pool.W + pool.U + pool.B + pool.R + pool.G + pool.C;
}
