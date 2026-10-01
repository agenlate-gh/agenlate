/**
 * The models a user can pick, and what they cost.
 *
 * A short curated list rather than OpenRouter's full catalogue, which is over
 * four hundred entries and mostly variants nobody running a roundtable wants.
 * Every id here was checked against OpenRouter's live catalogue; the prices are
 * per million tokens as listed there.
 *
 * This list is still hand-maintained, which means it can go stale. Replacing it
 * with a filtered view of the live catalogue is open work — it needs an
 * endpoint, because the browser cannot cache a 400-entry list per page load.
 */

export type ModelChoice = {
  /** The OpenRouter model id, sent to the API verbatim. */
  value: string
  label: string
  /** What this one is for, in the space of a line. */
  tier: string
}

/**
 * The default for running a room.
 *
 * Measured on the same room: Qwen 3.7 Flash finished in 19s for $0.0073,
 * DeepSeek in 86s for $0.0077, and Claude Sonnet cost $0.1181 — sixteen times
 * Qwen for no difference a user would notice on this kind of work. Under BYOK
 * the bill is the user's, so the default is the cheap one that was also the
 * fastest, and anyone who wants a stronger model can say so.
 */
export const DEFAULT_RUN_MODEL = 'qwen/qwen3.7-flash'

/** The default for the agent-building conversation. Matches the backend's. */
export const DEFAULT_BUILDER_MODEL = 'qwen/qwen3.7-flash'

/**
 * The one free model offered.
 *
 * It costs nothing, which matters to someone trying Agenlate before adding
 * credit: an OpenRouter account with no money in it can still run a room. The
 * label says what that costs in other ways, because it is a lot. Measured on
 * the same two-agent room: this model took 226 seconds where Qwen took 11, and
 * OpenRouter limits free models to 20 requests a minute and 50 a day per
 * account (1,000 once the account has ever bought $10 of credit).
 *
 * One, not several. Of three free models tried, one was refused outright and
 * one was rate-limited by its provider; offering models that mostly fail would
 * teach a new user that the product is unreliable.
 */
const FREE_MODEL: ModelChoice = {
  value: 'nvidia/nemotron-3.5-lightning:free',
  label: 'Nemotron 3.5 (free)',
  tier: 'Free, but slow — and limited to 50 requests a day',
}

export const runModels: ModelChoice[] = [
  {
    value: 'qwen/qwen3.7-flash',
    label: 'Qwen 3.7 Flash',
    tier: 'Fastest and cheapest — $0.03/$0.13 per M',
  },
  {
    value: 'deepseek/deepseek-v4-flash',
    label: 'DeepSeek V4 Flash',
    tier: 'Cheap, slower — $0.09/$0.18 per M',
  },
  {
    value: 'google/gemini-3.7-flash',
    label: 'Gemini 3.7 Flash',
    tier: 'Balanced — $0.75/$3.75 per M',
  },
  {
    value: 'anthropic/claude-sonnet-5',
    label: 'Claude Sonnet 5',
    tier: 'Strongest, costs most — $2/$10 per M',
  },
  FREE_MODEL,
]

/**
 * Models for the builder conversation.
 *
 * Deliberately only the cheap ones. Building an agent is a back-and-forth of
 * short turns, and paying Sonnet prices to be asked a clarifying question is
 * spending with nothing to show for it.
 */
export const builderModels: ModelChoice[] = [
  {
    value: 'qwen/qwen3.7-flash',
    label: 'Qwen 3.7 Flash',
    tier: 'Fast and cheap',
  },
  {
    value: 'deepseek/deepseek-v4-flash',
    label: 'DeepSeek V4 Flash',
    tier: 'Cheap alternative',
  },
  {
    value: 'google/gemini-3.7-flash',
    label: 'Gemini 3.7 Flash',
    tier: 'Better at long instructions',
  },
  FREE_MODEL,
]

export function labelFor(models: ModelChoice[], value: string): string {
  // An id we do not recognise is shown as itself rather than as nothing: the
  // list can lag OpenRouter's catalogue, and a blank selector is worse than an
  // unfamiliar name.
  return models.find((m) => m.value === value)?.label ?? value
}
