/**
 * How an agent looks: its initials and its colour.
 *
 * Neither is stored. An agent is a name, a role and a set of instructions —
 * asking a user to pick a colour for one would be a decision with no
 * consequence, and storing it would mean a schema column that exists only to
 * hold a preference nobody has.
 *
 * Both are derived from the agent instead, so the same agent looks the same on
 * every screen and across reloads without anything having to remember it.
 */

/**
 * Fixed palette rather than a generated hue. Arbitrary hues land on colours
 * that disappear against the dark background or read as an error state; these
 * are all legible on #0a0a0a and none of them is red.
 */
const PALETTE = [
  '#34d399', // green
  '#60a5fa', // blue
  '#f472b6', // pink
  '#a78bfa', // violet
  '#fbbf24', // amber
  '#22d3ee', // cyan
  '#fb923c', // orange
  '#4ade80', // lime
] as const

/** The Supervisor is not one of the user's agents, so it keeps the brand colour. */
export const SUPERVISOR_COLOR = '#fff41f'

function hash(value: string): number {
  // djb2. Any stable hash would do; what matters is that it does not change
  // between sessions, which rules out anything involving object identity.
  let h = 5381
  for (let i = 0; i < value.length; i += 1) {
    h = ((h << 5) + h + value.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

/** A colour for this agent, stable for the life of its id. */
export function agentColor(agentId: string): string {
  return PALETTE[hash(agentId) % PALETTE.length]
}

/**
 * Up to two letters from the name.
 *
 * "Code Auditor" gives CA, "Orquestador" gives OR. A name that is only
 * punctuation or emoji has no letters to take, so it falls back to a
 * placeholder rather than rendering an empty circle.
 */
export function agentInitials(name: string): string {
  const words = name
    .split(/\s+/)
    .map((word) => word.replace(/[^\p{L}\p{N}]/gu, ''))
    .filter(Boolean)

  if (words.length === 0) return '??'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[1][0]).toUpperCase()
}
