import { cleanTenantText } from "@/lib/tenant-guard";

/**
 * Display rules for backend strategy text. Everything passes the same banned-claims guard as tenant
 * text (lib/tenant-guard.ts); text that fails is hidden, never shown.
 */
type StrategyText = { name: string; description?: string | null; hypothesis?: string | null; hypothesis_id?: string | null };

const HYPOTHESIS_ID = /^H\d+$/i;
const squash = (s: string) => s.trim().replace(/\s+/g, " ").toLowerCase();

/** Subtitle: the description only when non-empty, guard-clean, and not just a repeat of the name. */
export function strategySubtitle(s: StrategyText): string | null {
  const d = cleanTenantText(s.description);
  if (!d || squash(d) === squash(s.name)) return null;
  return d;
}

export interface HypothesisDisplay {
  /** Small neutral tag next to the version, e.g. "H1". */
  tag: string | null;
  /** Full hypothesis text for the "Hypothesis" section. */
  text: string | null;
}

/**
 * Prefer `hypothesis_id` for the tag; until the backend sends it, a bare-id `hypothesis` ("H1") becomes
 * the tag instead of a "Hypothesis" section. A real sentence goes under the heading.
 */
export function strategyHypothesis(s: StrategyText): HypothesisDisplay {
  const id = cleanTenantText(s.hypothesis_id);
  const h = cleanTenantText(s.hypothesis);
  const hIsId = !!h && HYPOTHESIS_ID.test(h);
  const tag = id ?? (hIsId ? h! : null);
  const text = h && !hIsId ? h : null;
  return { tag: tag ? tag.toUpperCase().replace(/\s+/g, "") : null, text };
}
