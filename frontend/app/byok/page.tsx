'use client'

import { TopNavbar } from '@/components/top-navbar'
import { LobbySidebar } from '@/components/lobby-sidebar'
import { CircleOff, Eye, EyeOff, Key, Plus } from 'lucide-react'
import { useState } from 'react'

/**
 * Official OpenRouter API key prefix.
 * Agenlate validates against this prefix strictly so that real-time web
 * scraping and the financial meter always resolve through the OpenRouter
 * network — keys from any other provider are rejected before being stored.
 */
const OPENROUTER_KEY_PREFIX = 'sk-or-v1-'

/** Educational message shown whenever the pasted key is not an OpenRouter key. */
const BYOK_FORMAT_ERROR =
  'Agenlate works only through the OpenRouter network, which is what makes web search and the spending meter work. Please enter a key beginning with sk-or-v1-'

export default function ByokPage() {
  const [apiKeys, setApiKeys] = useState<string[]>([])
  const [currentKey, setCurrentKey] = useState('')
  const [showKey, setShowKey] = useState(false)

  const trimmedKey = currentKey.trim()
  const hasInput = trimmedKey.length > 0
  const isOpenRouterKey = trimmedKey.startsWith(OPENROUTER_KEY_PREFIX)

  /**
   * Pedantic validation: any format that is not "sk-or-v1-..." — OpenAI's
   * "sk-proj-...", other gateways or generic text — triggers the error state.
   */
  const showFormatError = hasInput && !isOpenRouterKey

  function handleAddKey() {
    if (!isOpenRouterKey) return
    setApiKeys([...apiKeys, trimmedKey])
    setCurrentKey('')
  }

  const fieldClass = showFormatError
    ? 'border-[#DC2626] ring-1 ring-[#DC2626]/25 focus:border-[#DC2626] dark:border-[#EF4444] dark:ring-[#EF4444]/40 dark:focus:border-[#EF4444]'
    : 'border-[#E4E4E7] focus:border-[#111111]/30 dark:border-[#262629] dark:focus:border-[#FFF41F]/50'

  return (
    <div className="flex h-screen max-h-screen w-full flex-col overflow-hidden bg-[#0a0a0a] text-foreground">
      <TopNavbar />

      <div className="flex min-h-0 flex-1 pt-[56px]">
        <div className="hidden md:flex">
          <LobbySidebar />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-6 overflow-y-auto pl-16 pr-6 pt-12 pb-6">
          <div className="w-full max-w-3xl">
            {/* Header */}
            <div className="mb-10">
              <h1 className="flex items-center gap-2.5 text-[20px] font-semibold tracking-tight text-[#111111] dark:text-white">
                <Key className="size-5 text-[#7A6F00] dark:text-[#FFF41F]" strokeWidth={1.5} />
                BYOK Console
              </h1>
              <p className="mt-1.5 text-[13px] font-light leading-relaxed text-[#52525B] dark:text-[#7d7d82]">
                Bring your own API Key from OpenRouter to unlock secure web scraping and direct LLM interconnectivity within your workspaces.
              </p>
            </div>

            {/* Add API Key — flat, no card */}
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-[13px] font-semibold text-[#111111] dark:text-white">
                OpenRouter API Key
              </h3>
              <span className="flex items-center gap-1.5 text-[11px] text-green-600 dark:text-green-500">
                <span className="size-1.5 rounded-full bg-green-600 pulse-dot dark:bg-green-500" aria-hidden />
                Live Network
              </span>
            </div>

            <div className={`mb-3 flex items-center gap-3 rounded-lg border bg-[#141414] px-4 py-2.5 transition-all focus-within:border-[#FFF41F]/50 dark:bg-[#141414] dark:focus-within:border-[#FFF41F]/50 ${
                  showFormatError
                    ? 'border-[#DC2626] dark:border-[#EF4444]'
                    : 'border-[#16161a] dark:border-[#16161a]'
                }`}>
              <input
                type={showKey ? 'text' : 'password'}
                value={currentKey}
                onChange={(e) => setCurrentKey(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddKey()}
                placeholder="sk-or-v1-..."
                aria-label="OpenRouter API Key"
                aria-invalid={showFormatError}
                aria-describedby={showFormatError ? 'byok-key-error' : 'byok-key-hint'}
                className={`flex-1 border-0 bg-transparent text-[14px] font-mono text-foreground outline-none placeholder:text-[#A1A1AA] ${
                  showFormatError ? 'text-[#DC2626] dark:text-[#EF4444]' : ''
                }`}
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="shrink-0 text-[#71717A] hover:text-[#111111] dark:text-[#7d7d82] dark:hover:text-white"
                aria-label={showKey ? 'Hide key' : 'Show key'}
              >
                {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>

              {showFormatError && (
                <div
                  id="byok-key-error"
                  role="alert"
                  className="mb-2 flex items-start gap-2"
                >
                  <CircleOff className="mt-0.5 size-3.5 shrink-0 text-[#DC2626] dark:text-[#F87171]" />
                  <p className="text-[11.5px] font-light leading-relaxed text-[#991B1B] dark:text-[#FCA5A5]">
                    <span className="font-medium text-[#B91C1C] dark:text-[#F87171]">Error:</span>{' '}
                    {BYOK_FORMAT_ERROR}
                  </p>
                </div>
              )}

              {isOpenRouterKey && (
                <p className="mb-2 flex items-center gap-1.5 text-[11.5px] font-light text-green-600 dark:text-green-500">
                  <span className="size-1.5 rounded-full bg-green-600 dark:bg-green-500" aria-hidden />
                  Valid OpenRouter format · prefix <span className="font-mono">sk-or-v1-</span>
                </p>
              )}

              {!hasInput && (
                <p
                  id="byok-key-hint"
                  className="mb-2 text-[11px] font-light leading-relaxed text-[#A1A1AA] dark:text-[#7d7d82]"
                >
                  Required format:{' '}
                  <span className="font-mono font-semibold text-[#52525B] dark:text-[#7d7d82]">
                    sk-or-v1-...
                  </span>{' '}
                  · Keys from other providers (for example{' '}
                  <span className="font-mono">sk-proj-...</span>) are rejected.
                </p>
              )}

              <button
                type="button"
                onClick={handleAddKey}
                disabled={!isOpenRouterKey}
                className="inline-flex items-center gap-1.5 rounded-md bg-[#FFF41F] px-3 py-1.5 text-[12px] font-semibold text-[#111111] transition-all hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50 dark:text-[#0A0A0A]"
              >
                <Plus className="size-3.5" strokeWidth={2.5} />
                Add API Key
              </button>

            {/* Guide — flat, flows directly on background */}
            <div className="mt-6">
              <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-[#52525B] dark:text-[#7d7d82]">
                Quick Guide
              </h3>
              <ul className="space-y-2 text-[12.5px] font-light leading-relaxed text-[#52525B] dark:text-[#7d7d82]">
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 font-semibold text-[#7d7d82]">1.</span>
                  <span>Visit <span className="font-medium text-[#111111] dark:text-white">openrouter.ai/keys</span> and sign in to your account.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 font-semibold text-[#7d7d82]">2.</span>
                  <span>Generate a new API key. It must start with the official <span className="font-mono text-[#111111] dark:text-white">sk-or-v1-</span> prefix.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 font-semibold text-[#7d7d82]">3.</span>
                  <span>Copy it and paste it into the field above. Never share your key with third parties.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="mt-0.5 font-semibold text-[#7d7d82]">4.</span>
                  <span>Click <span className="font-medium text-[#111111] dark:text-white">Add API Key</span> to activate it in your session.</span>
                </li>
              </ul>
            </div>

            {/* Stored keys — flat */}
            {apiKeys.length > 0 && (
              <div className="mt-4 pt-2">
                <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-[#52525B] dark:text-[#7d7d82]">
                  Stored Keys ({apiKeys.length})
                </h3>
                <div className="space-y-2">
                  {apiKeys.map((key, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between border-b border-[#16161a] pb-2"
                    >
                      <span className="font-mono text-[12px] text-[#52525B] dark:text-[#7d7d82]">
                        {key.slice(0, 12)}...
                      </span>
                      <span className="flex items-center gap-1.5 text-[11px] text-green-600 dark:text-green-500">
                        <span className="size-1.5 rounded-full bg-green-600 dark:bg-green-500" />
                        Connected
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
