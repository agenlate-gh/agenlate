'use client'

/**
 * Work in progress, kept so it cannot be lost.
 *
 * A long instruction to the builder is real work, and so is the conversation
 * it belongs to. If the screen crashes, the tab reloads, or the user goes off
 * to add their API key and comes back, both should still be there. They are
 * held in sessionStorage — this tab only, gone when the tab closes — and
 * cleared by the caller once the work is finished.
 *
 * sessionStorage rather than localStorage: a draft is not worth keeping for
 * weeks, and it should not appear in another tab's copy of the same form.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

const PREFIX = 'agenlate.draft.'

/**
 * State that survives a reload of this tab.
 *
 * Like `useState`, with a storage key. An empty string, null, or an empty
 * array removes the stored entry rather than storing "nothing".
 */
export function useStored<T>(key: string, initial: T): [T, (next: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(initial)
  const latest = useRef(value)
  latest.current = value

  // Restored after mount rather than during render: the server renders these
  // screens first and has no storage, so reading it any earlier would make the
  // first client render disagree with the server's.
  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem(PREFIX + key)
      if (saved !== null) setValue(JSON.parse(saved) as T)
    } catch {
      // Storage blocked or the entry unreadable: start from the initial value.
    }
  }, [key])

  const update = useCallback(
    (next: T | ((prev: T) => T)) => {
      const resolved =
        typeof next === 'function' ? (next as (prev: T) => T)(latest.current) : next
      latest.current = resolved
      setValue(resolved)
      try {
        const empty =
          resolved === null ||
          resolved === '' ||
          (Array.isArray(resolved) && resolved.length === 0)
        if (empty) window.sessionStorage.removeItem(PREFIX + key)
        else window.sessionStorage.setItem(PREFIX + key, JSON.stringify(resolved))
      } catch {
        // Storage blocked: the value lives in memory only, as it did before.
      }
    },
    [key],
  )

  return [value, update]
}

/** Text someone is in the middle of typing. */
export function useDraft(key: string): [string, (next: string) => void] {
  return useStored<string>(key, '')
}
