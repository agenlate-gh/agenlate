'use client'

/**
 * What the user has spent.
 *
 * Not a wallet. Under BYOK there is no Agenlate balance to show and nothing to
 * top up — the user's credit sits at OpenRouter and is spent from there
 * directly. So this screen reports rather than transacts, and the one action
 * it offers is a link to where the credit actually lives.
 *
 * It also does not lead with token volume. Measured on the same room, a run
 * cost $0.000179 with web search off and $0.007285 with it on: a factor of
 * forty, almost none of it tokens. Two users with identical token counts can
 * differ by that much, so the split that matters is how much came from calls
 * that could reach the web, and that is reported on its own.
 */

import { useCallback, useEffect, useState } from 'react'
import { CreditCard, ExternalLink, Wallet } from 'lucide-react'

import { RequireAuth } from '@/components/auth-provider'
import { ConsumptionChart } from '@/components/consumption-chart'
import { LobbySidebar } from '@/components/lobby-sidebar'
import { TopNavbar } from '@/components/top-navbar'
import type { DailyUsage, UsageEvent, UsageSummary } from '@/lib/agenlate'
import { usage as usageApi } from '@/lib/agenlate'
import { ApiError } from '@/lib/api'
import { formatUsd, timeAgo } from '@/lib/format'

const WINDOWS = [
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
] as const

export default function BillingPage() {
  return (
    <RequireAuth>
      <Billing />
    </RequireAuth>
  )
}

function Billing() {
  const [days, setDays] = useState<number>(30)
  const [summary, setSummary] = useState<UsageSummary | null>(null)
  const [series, setSeries] = useState<DailyUsage[]>([])
  const [events, setEvents] = useState<UsageEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (window: number) => {
    setError(null)
    try {
      const [totals, daily, log] = await Promise.all([
        usageApi.summary(window),
        usageApi.daily(window),
        usageApi.events(window),
      ])
      setSummary(totals)
      setSeries(daily)
      setEvents(log)
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'Could not load your usage.',
      )
    }
  }, [])

  useEffect(() => {
    void load(days)
  }, [days, load])

  // Nothing has arrived yet. Distinct from "arrived and is zero": showing
  // $0.0000 while the request is in flight tells a user who has spent money
  // that they have not.
  const loading = summary === null && !error

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
                <CreditCard
                  className="size-5 text-[#7A6F00] dark:text-[#FFF41F]"
                  strokeWidth={1.5}
                />
                Billing
              </h1>
              <p className="mt-1.5 max-w-2xl text-[13px] font-light leading-relaxed text-[#52525B] dark:text-[#7d7d82]">
                What your agents have spent on your own OpenRouter key. Agenlate
                does not hold a balance for you and takes no cut — your credit
                lives at OpenRouter and is spent from there directly.
              </p>
            </div>

            {error && (
              <div
                role="alert"
                className="mb-6 flex items-center justify-between gap-4 rounded-lg border border-red-500/20 bg-red-950/20 px-4 py-3"
              >
                <p className="text-[13px] font-light text-[#FCA5A5]">{error}</p>
                <button
                  type="button"
                  onClick={() => void load(days)}
                  className="shrink-0 text-[12px] font-medium text-[#FFF41F] transition-opacity hover:opacity-80"
                >
                  Try again
                </button>
              </div>
            )}

            <SpentPanel summary={summary} days={days} loading={loading} />

            <div className="mb-4 flex items-center gap-2 px-1">
              {WINDOWS.map((window) => (
                <button
                  key={window.days}
                  type="button"
                  onClick={() => setDays(window.days)}
                  aria-pressed={days === window.days}
                  className={`rounded-md border px-3 py-1.5 text-[12px] font-medium transition-colors ${
                    days === window.days
                      ? 'border-[#FFF41F]/40 bg-[#FFF41F]/10 text-[#FFF41F]'
                      : 'border-[#16161a] bg-[#141414] text-[#7d7d82] hover:text-white'
                  }`}
                >
                  Last {window.label}
                </button>
              ))}
            </div>

            <div className="mb-6">
              {loading ? (
                <div className="h-[226px] animate-pulse rounded-lg border border-[#262629] bg-[#0f0f0f]" aria-hidden />
              ) : (
                <ConsumptionChart series={series} />
              )}
            </div>

            <AuditLog events={events} loading={loading} />
          </div>
        </div>
      </div>
    </div>
  )
}

function SpentPanel({
  summary,
  days,
  loading,
}: {
  summary: UsageSummary | null
  days: number
  loading: boolean
}) {
  const spent = summary?.cost_usd ?? 0
  // A total is a floor rather than a total whenever the provider left calls
  // unpriced. Showing it as exact would understate what the user spent.
  const incomplete = summary ? !summary.cost_is_complete : false

  return (
    <div className="mb-6 rounded-xl bg-[#141414] px-5 pb-6 pt-5">
      <div className="mb-3 flex items-center gap-2">
        <Wallet className="size-4 text-[#7d7d82]" strokeWidth={1.5} />
        <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[#7d7d82]">
          Spent in the last {days} days
        </h3>
      </div>

      <div className="flex flex-wrap items-baseline gap-3">
        {loading ? (
          <span
            className="inline-block h-[40px] w-40 animate-pulse rounded-md bg-[#1f1f23]"
            aria-label="Loading what you have spent"
          />
        ) : (
          <span className="text-[36px] font-semibold tracking-tight text-white">
            {incomplete && <span className="text-[24px] text-[#7d7d82]">at least </span>}
            {/* A dash when the request failed: the error above says why, and
                a zero here would contradict it. */}
            {summary ? formatUsd(spent) : '—'}
          </span>
        )}
        <span className="text-[15px] font-light text-[#a1a1aa]">USD</span>
        <a
          href="https://openrouter.ai/credits"
          target="_blank"
          rel="noreferrer"
          className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-[#FFF41F] px-4 py-2 text-[13px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95"
        >
          Add credit at OpenRouter
          <ExternalLink className="size-3.5" strokeWidth={2} />
        </a>
      </div>

      {summary && (
        <div className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-[#1f1f23] pt-4 sm:grid-cols-3">
          <Stat label="Rooms active" value={summary.rooms.toLocaleString()} />
          <Stat label="Requests" value={summary.requests.toLocaleString()} />
          <Stat
            label="Of that, web-enabled"
            value={formatUsd(summary.tool_enabled_cost_usd)}
            note={`${summary.tool_enabled_requests} request${
              summary.tool_enabled_requests === 1 ? '' : 's'
            } that could reach the web`}
          />
        </div>
      )}

      {incomplete && summary && (
        <p className="mt-4 text-[11.5px] font-light leading-relaxed text-[#7d7d82]">
          {summary.unpriced_requests} request
          {summary.unpriced_requests === 1 ? ' was' : 's were'} not priced by the
          provider, so the real figure is higher than the one above. OpenRouter
          is the authority on what you were actually charged.
        </p>
      )}
    </div>
  )
}

function Stat({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note?: string
}) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-[10px] font-medium uppercase tracking-wider text-[#7d7d82]">
        {label}
      </span>
      <span className="mt-1 font-mono text-[15px] font-semibold tabular-nums text-white">
        {value}
      </span>
      {note && (
        <span className="mt-0.5 text-[10.5px] font-light leading-snug text-[#7d7d82]">
          {note}
        </span>
      )}
    </div>
  )
}

function AuditLog({ events, loading }: { events: UsageEvent[]; loading: boolean }) {
  return (
    <div className="mb-6 px-1">
      <h3 className="mb-4 text-[12px] font-semibold uppercase tracking-wide text-[#7d7d82]">
        Consumption Audit Log
      </h3>

      {loading ? (
        <p className="text-[12.5px] font-light leading-relaxed text-[#7d7d82]">
          Loading your provider calls…
        </p>
      ) : events.length === 0 ? (
        <p className="text-[12.5px] font-light leading-relaxed text-[#7d7d82]">
          Nothing to show for this window. Every provider call your agents make
          is listed here as it happens.
        </p>
      ) : (
        <div className="scrollbar-thin max-h-[280px] overflow-y-auto overflow-x-auto rounded-lg border border-[#16161a]">
          <table className="w-full text-left text-[12px]">
            <thead>
              <tr className="border-b border-[#16161a] text-[10px] font-medium uppercase tracking-wider text-[#7d7d82]">
                <Th>USD Spent</Th>
                <Th>Workspace</Th>
                <Th>Spoken by</Th>
                <Th>Model</Th>
                <Th>When</Th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr
                  key={event.id}
                  className="border-b border-[#16161a] transition-colors hover:bg-white/5"
                >
                  <td className="px-2 py-3 font-mono text-[13px] font-semibold tabular-nums text-white">
                    {event.cost_usd === null || event.cost_usd === undefined ? (
                      <span
                        className="text-[#7d7d82]"
                        title="The provider did not price this call."
                      >
                        not priced
                      </span>
                    ) : (
                      formatUsd(event.cost_usd)
                    )}
                  </td>
                  <td className="px-2 py-3 text-white">
                    {/* Null once the room is deleted; the spending still
                        happened, so the row stays. */}
                    {event.room_name ?? (
                      <span className="text-[#7d7d82]">deleted room</span>
                    )}
                  </td>
                  <td className="px-2 py-3 text-white">
                    {event.emitter_name ?? <span className="text-[#7d7d82]">—</span>}
                  </td>
                  <td className="px-2 py-3 font-mono text-[11px] text-[#7d7d82]">
                    {event.model}
                  </td>
                  <td className="px-2 py-3 text-[11px] text-[#7d7d82]">
                    {timeAgo(event.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="sticky top-0 bg-[#0A0A0A] px-2 pb-2.5 pt-2.5 font-medium">
      {children}
    </th>
  )
}
