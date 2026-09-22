/**
 * Where the user's OpenRouter key lives: this browser, and nowhere else.
 *
 * Agenlate is bring-your-own-key. The key is sent with each run request, used
 * for the duration of that request and dropped — the backend never writes it
 * down. Keeping it here rather than in our database is the whole point of that
 * arrangement: a breach of Agenlate exposes no one's provider credit.
 *
 * The cost is that it does not follow the user between browsers or devices,
 * and clearing site data loses it. That is the trade, and the BYOK screen says
 * so rather than letting a user discover it when a run fails on their laptop.
 *
 * localStorage rather than sessionStorage: a key the user re-enters every time
 * they open a tab is a key they will paste from somewhere less careful.
 */

const STORAGE_KEY = 'agenlate.openrouter-key'

/**
 * Whether a value is plausibly a key, so an obvious mistake is caught before a
 * request is made.
 *
 * Shape only, and deliberately the same rule as `looks_like_openrouter_key` in
 * the backend — a stricter one here would reject keys the API accepts and send
 * the user looking for a fault that is ours. A well-formed key can still be
 * revoked or out of credit, which is what the validate endpoint is for.
 */
const KEY_PREFIX = 'sk-or-v1-'
const MIN_KEY_LENGTH = 24

export function looksLikeOpenRouterKey(key: string): boolean {
  const value = key.trim()
  return value.startsWith(KEY_PREFIX) && value.length >= MIN_KEY_LENGTH
}

/**
 * The stored key, or null.
 *
 * Every access is guarded: storage throws rather than returning null when a
 * browser blocks site data, and a run screen that crashes on that is worse
 * than one that asks for the key again.
 */
export function readKey(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function saveKey(key: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, key.trim())
  } catch {
    // Nothing useful to do. The caller has the key in memory either way, and
    // the alternative is refusing to start a run over a storage preference.
  }
}

export function clearKey(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // As above.
  }
}

/**
 * The last four characters, for showing which key is stored.
 *
 * Never the whole key. A screen that prints it invites a screenshot, and the
 * tail is enough to tell two keys apart.
 */
export function keyTail(key: string): string {
  return `…${key.trim().slice(-4)}`
}
