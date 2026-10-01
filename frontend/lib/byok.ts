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
 *
 * Stored per account, not per browser. People do sign in on a borrowed
 * laptop, and a key stored for the browser as a whole would be picked up —
 * and spent from — by the next person to sign in there. Under an account's
 * own slot it stays put for its owner across sign-outs and is invisible to
 * anyone else's account. It is still on that machine until removed, which the
 * BYOK screen says.
 */

const STORAGE_PREFIX = 'agenlate.openrouter-key'

/** The slot used before keys were per account. Removed on sight. */
const LEGACY_KEY = 'agenlate.openrouter-key'

let owner: string | null = null

function slot(userId: string): string {
  return `${STORAGE_PREFIX}.${userId}`
}

/**
 * Says whose key the functions below read and write. Called by the auth
 * provider whenever the session changes, before anything renders for the new
 * session — so no screen can read a key belonging to the previous account.
 */
export function setKeyOwner(userId: string | null): void {
  owner = userId
  try {
    // A key saved before keys were per account has no owner we can know. It
    // is deleted rather than given to whoever signs in next, which would be
    // exactly the leak this is here to prevent; its owner re-enters it once.
    window.localStorage.removeItem(LEGACY_KEY)
  } catch {
    // Storage unavailable: nothing was stored, so nothing to remove.
  }
}

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
  if (!owner) return null
  try {
    return window.localStorage.getItem(slot(owner))
  } catch {
    return null
  }
}

export function saveKey(key: string): void {
  if (!owner) return
  try {
    window.localStorage.setItem(slot(owner), key.trim())
  } catch {
    // Nothing useful to do. The caller has the key in memory either way, and
    // the alternative is refusing to start a run over a storage preference.
  }
}

export function clearKey(): void {
  if (!owner) return
  try {
    window.localStorage.removeItem(slot(owner))
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
