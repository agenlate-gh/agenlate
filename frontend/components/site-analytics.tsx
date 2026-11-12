'use client'

/**
 * Page-view counting (Vercel Web Analytics), with invite codes taken out.
 *
 * An invite link carries its code in the address. A single-use code is a
 * credential, so it must never leave the browser in an analytics event. Each
 * link is recorded instead as a made-up page naming where it was shared —
 * `/login/via/reddit` — which is also what we want to count: how many people
 * opened each channel's link, whether or not they then signed up.
 *
 * The fragment is dropped too: password-reset and confirmation links put
 * session tokens there.
 */

import { Analytics, type BeforeSendEvent } from '@vercel/analytics/next'

// The shared channel codes. Public already: they are posted in the open.
const CHANNELS: Record<string, string> = {
  'K4F3-5BF3-WUM8': 'reddit',
  'JQE4-Q756-GUSC': 'discord',
  '3M8N-KJX9-WFAB': 'whatsapp',
  'FPA4-FY8C-C75M': 'x',
  '4QKB-6N94-AFNX': 'linkedin',
}

function channelOf(typed: string): string {
  const compact = typed.toUpperCase().replace(/[^A-Z0-9]/g, '')
  const code = compact.match(/.{1,4}/g)?.join('-') ?? ''
  return CHANNELS[code] ?? 'single-code'
}

export function scrub(event: BeforeSendEvent): BeforeSendEvent {
  const url = new URL(event.url)
  url.hash = ''
  const invite = url.searchParams.get('invite')
  if (invite !== null) {
    url.pathname = `/login/via/${channelOf(invite)}`
    url.search = ''
  }
  return { ...event, url: url.toString() }
}

export function SiteAnalytics() {
  return <Analytics beforeSend={scrub} />
}
