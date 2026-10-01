'use client'

/**
 * Where the user gives Agenlate their OpenRouter key.
 *
 * One key, not a list. The key is what pays for runs, and there is exactly one
 * account paying — offering to store several would be offering a choice with
 * no meaning behind it, since nothing decides which one a run uses.
 *
 * The key is checked against OpenRouter before it is stored. That check is
 * free: OpenRouter's key endpoint reports whether a key works without running
 * any inference. Catching a bad key here turns what would otherwise be a
 * failed run — after building agents, opening a room and pressing go — into a
 * form error.
 */

import { useEffect, useState } from 'react'
import { CircleOff, Eye, EyeOff, Key, Loader2, Trash2 } from 'lucide-react'

import { RequireAuth } from '@/components/auth-provider'
import { LobbySidebar } from '@/components/lobby-sidebar'
import { TopNavbar } from '@/components/top-navbar'
import { keys as keysApi } from '@/lib/agenlate'
import { ApiError } from '@/lib/api'
import { clearKey, keyTail, looksLikeOpenRouterKey, readKey, saveKey } from '@/lib/byok'

const FORMAT_ERROR =
  'Agenlate runs through OpenRouter, which is what makes web search and the spending meter work. Enter a key beginning with sk-or-v1-'

export default function ByokPage() {
  return (
    <RequireAuth>
      <Byok />
    </RequireAuth>
  )
}

function Byok() {
  const [stored, setStored] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [visible, setVisible] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState<string | null>(null)

  // Reading storage on mount rather than during render: the server renders
  // this page first and has no localStorage, so touching it any earlier is a
  // hydration mismatch.
  useEffect(() => setStored(readKey()), [])

  const trimmed = draft.trim()
  const wellFormed = looksLikeOpenRouterKey(trimmed)
  const showFormatError = trimmed.length > 0 && !wellFormed

  async function save() {
    if (!wellFormed || checking) return
    setChecking(true)
    setError(null)
    setConfirmation(null)

    try {
      const result = await keysApi.validate(trimmed)
      if (!result.valid) {
        setError(result.message)
        return
      }

      saveKey(trimmed)
      setStored(trimmed)
      setDraft('')
      setVisible(false)
      setConfirmation(
        result.limit_remaining !== null && result.limit_remaining !== undefined
          ? `${result.message} $${result.limit_remaining.toFixed(2)} of credit left on it.`
          : result.message,
      )
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'Could not check this key.',
      )
    } finally {
      setChecking(false)
    }
  }

  function remove() {
    clearKey()
    setStored(null)
    setConfirmation(null)
    setError(null)
  }

  return (
    <div className="flex h-screen max-h-screen w-full flex-col overflow-hidden bg-[#0a0a0a] text-foreground">
      <TopNavbar />

      <div className="flex min-h-0 flex-1 pt-[56px]">
        <div className="hidden md:flex">
          <LobbySidebar />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-6 overflow-y-auto pl-16 pr-6 pt-12 pb-6">
          <div className="w-full max-w-3xl">
            <div className="mb-10">
              <h1 className="flex items-center gap-2.5 text-[20px] font-semibold tracking-tight text-[#111111] dark:text-white">
                <Key className="size-5 text-[#7A6F00] dark:text-[#FFF41F]" strokeWidth={1.5} />
                BYOK Console
              </h1>
              <p className="mt-1.5 max-w-2xl text-[13px] font-light leading-relaxed text-[#52525B] dark:text-[#7d7d82]">
                Agenlate runs on your own OpenRouter key. Your agents spend your
                credit directly, and we never take a cut of it or hold it on
                your behalf.
              </p>
            </div>

            {stored ? (
              <ConnectedKey tail={keyTail(stored)} onRemove={remove} />
            ) : (
              <>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-[13px] font-semibold text-[#111111] dark:text-white">
                    OpenRouter API Key
                  </h3>
                </div>

                <div
                  className={`mb-3 flex items-center gap-3 rounded-lg border bg-[#141414] px-4 py-2.5 transition-all focus-within:border-[#FFF41F]/50 ${
                    showFormatError ? 'border-[#EF4444]' : 'border-[#16161a]'
                  }`}
                >
                  <input
                    type={visible ? 'text' : 'password'}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => event.key === 'Enter' && void save()}
                    placeholder="sk-or-v1-..."
                    aria-label="OpenRouter API key"
                    aria-invalid={showFormatError}
                    aria-describedby={showFormatError ? 'byok-error' : 'byok-hint'}
                    autoComplete="off"
                    spellCheck={false}
                    className="flex-1 border-0 bg-transparent font-mono text-[14px] text-foreground outline-none placeholder:text-[#52525B]"
                  />
                  <button
                    type="button"
                    onClick={() => setVisible(!visible)}
                    aria-label={visible ? 'Hide key' : 'Show key'}
                    className="shrink-0 text-[#7d7d82] transition-colors hover:text-white"
                  >
                    {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>

                {showFormatError && (
                  <div id="byok-error" role="alert" className="mb-2 flex items-start gap-2">
                    <CircleOff className="mt-0.5 size-3.5 shrink-0 text-[#F87171]" />
                    <p className="text-[11.5px] font-light leading-relaxed text-[#FCA5A5]">
                      {FORMAT_ERROR}
                    </p>
                  </div>
                )}

                {error && (
                  <p role="alert" className="mb-2 text-[11.5px] font-light leading-relaxed text-[#FCA5A5]">
                    {error}
                  </p>
                )}

                {!trimmed && (
                  <p
                    id="byok-hint"
                    className="mb-2 text-[11px] font-light leading-relaxed text-[#7d7d82]"
                  >
                    Keys from other providers (for example{' '}
                    <span className="font-mono">sk-proj-…</span>) will not work.
                  </p>
                )}

                <button
                  type="button"
                  onClick={() => void save()}
                  disabled={!wellFormed || checking}
                  className="inline-flex items-center gap-1.5 rounded-md bg-[#FFF41F] px-3.5 py-2 text-[12px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {checking && <Loader2 className="size-3.5 animate-spin" />}
                  <span>{checking ? 'Checking with OpenRouter…' : 'Check and save key'}</span>
                </button>
              </>
            )}

            {confirmation && (
              <p className="mt-3 flex items-center gap-1.5 text-[11.5px] font-light text-green-500">
                <span className="size-1.5 rounded-full bg-green-500" aria-hidden />
                {confirmation}
              </p>
            )}

            <WhereItLives />
            <QuickGuide />
          </div>
        </div>
      </div>
    </div>
  )
}

function ConnectedKey({ tail, onRemove }: { tail: string; onRemove: () => void }) {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[13px] font-semibold text-[#111111] dark:text-white">
          OpenRouter API Key
        </h3>
        <span className="flex items-center gap-1.5 text-[11px] text-green-500">
          <span className="size-1.5 rounded-full bg-green-500 pulse-dot" aria-hidden />
          Connected
        </span>
      </div>

      <div className="flex items-center justify-between gap-4 rounded-lg border border-[#16161a] bg-[#141414] px-4 py-3">
        <span className="font-mono text-[13px] text-[#d4d4d8]">
          sk-or-v1-••••••••{tail}
        </span>
        <button
          type="button"
          onClick={onRemove}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium text-[#7d7d82] transition-colors hover:bg-red-950/30 hover:text-red-400"
        >
          <Trash2 className="size-3.5" strokeWidth={1.5} />
          Remove
        </button>
      </div>

      <p className="mt-2 text-[11.5px] font-light leading-relaxed text-[#7d7d82]">
        Only the last four characters are shown. Removing it here stops runs
        until you add one again; it does not revoke the key at OpenRouter.
      </p>
    </div>
  )
}

/**
 * The part users are entitled to know before pasting a credential.
 *
 * Stated plainly rather than buried: the key lives in this browser, which is
 * both the reason a breach of Agenlate exposes nobody's credit and the reason
 * it does not follow them to another machine.
 */
function WhereItLives() {
  return (
    <div className="mt-8 rounded-lg border border-[#16161a] bg-[#111111] px-4 py-3.5">
      <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[#d4d4d8]">
        Where this key lives
      </h3>
      <ul className="mt-2 space-y-1.5 text-[12px] font-light leading-relaxed text-[#7d7d82]">
        <li>
          It is stored in this browser. We never write it to our database, and
          a breach of Agenlate would not expose it.
        </li>
        <li>
          It is sent with each run, used for that run, and dropped. Nothing
          keeps a copy between runs.
        </li>
        <li>
          Because it lives here, it does not follow you to another browser or
          device, and clearing site data removes it.
        </li>
        <li>
          It is saved for your account only: someone else signing in on this
          browser cannot use it. On a computer that is not yours, remove it
          before you leave — signing out keeps it for your next visit.
        </li>
      </ul>
    </div>
  )
}

function QuickGuide() {
  const steps = [
    <>
      Visit{' '}
      <a
        href="https://openrouter.ai/keys"
        target="_blank"
        rel="noreferrer"
        className="font-medium text-[#FFF41F] transition-opacity hover:opacity-80"
      >
        openrouter.ai/keys
      </a>{' '}
      and sign in.
    </>,
    <>
      Create a key. It starts with{' '}
      <span className="font-mono text-white">sk-or-v1-</span>.
    </>,
    <>Add credit to your OpenRouter account — runs spend from it directly.</>,
    <>Paste the key above. We check it with OpenRouter before saving it.</>,
  ]

  return (
    <div className="mt-6">
      <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-[#7d7d82]">
        Quick Guide
      </h3>
      <ol className="space-y-2 text-[12.5px] font-light leading-relaxed text-[#7d7d82]">
        {steps.map((step, index) => (
          <li key={index} className="flex items-start gap-2">
            <span className="mt-0.5 font-semibold text-[#7d7d82]">{index + 1}.</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
