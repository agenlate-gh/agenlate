import { Analytics } from '@vercel/analytics/next'

import { AuthProvider } from '@/components/auth-provider'
import { WakeBackend } from '@/components/wake-backend'
import type { Metadata, Viewport } from 'next'
import { Plus_Jakarta_Sans, Poppins } from 'next/font/google'
import './globals.css'

/**
 * Blocking, pre-paint theme bootstrap.
 *
 * Dark is the default. Every screen paints a dark background of its own, and
 * most text colours only switch to light under the `dark` class — so in light
 * mode headings rendered near-black on near-black and the top bar was the one
 * white strip on the page. Light mode is kept only for someone who has
 * explicitly stored it. Set before first paint so there is no flash.
 */
const themeInitScript = `(function(){var root=document.documentElement;var dark=true;try{dark=window.localStorage.getItem('agenlate-theme')!=='light'}catch(e){}root.classList.toggle('dark',dark);root.style.colorScheme=dark?'dark':'light'})()`

/**
 * Keeps a translated page from crashing.
 *
 * Browser translation (Chrome offers it on every English page to anyone whose
 * language is not English) replaces text nodes with elements of its own. React
 * still holds the originals, and when it later inserts something beside one, or
 * removes one, the browser throws: "the node before which the new node is to be
 * inserted is not a child of this node". React treats that as fatal and the
 * whole screen is replaced by "This page couldn't load".
 *
 * With these two guards the operation is carried out in the nearest sensible
 * way instead of throwing: a removal of a node that already moved is skipped,
 * and an insertion whose anchor moved is appended. A spinner landing after its
 * label rather than before it is a cosmetic slip; losing the page — and
 * whatever the person had typed into it — is not.
 *
 * Runs before React, in the head, so it is in place for the first render.
 */
const domGuardScript = `(function(){if(typeof Node!=='function'||!Node.prototype)return;var rm=Node.prototype.removeChild;Node.prototype.removeChild=function(c){if(c&&c.parentNode!==this){return c}return rm.apply(this,arguments)};var ins=Node.prototype.insertBefore;Node.prototype.insertBefore=function(n,r){if(r&&r.parentNode!==this){return ins.call(this,n,null)}return ins.apply(this,arguments)}})()`

const poppins = Poppins({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-poppins',
  display: 'swap',
})

// The brand typeface, per the brand kit. Used for the wordmark and the public
// landing page; the signed-in app still sets its text in Poppins.
const jakarta = Plus_Jakarta_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-jakarta',
  display: 'swap',
})

export const metadata: Metadata = {
  metadataBase: new URL('https://agenlate.com'),
  // Just the name in the browser tab: with several tabs open only the first
  // word or two is visible. The tagline lives in the link preview below.
  title: 'Agenlate',
  description:
    'Build a team of AI agents by describing it in plain words. A Supervisor coordinates them, you watch every step, and you pay only what the models cost on your own key.',
  openGraph: {
    title: 'Agenlate — Describe the team. Watch it work.',
    description:
      'Build a team of AI agents in plain words, watch them work together, and see the cost of every step.',
    url: 'https://agenlate.com',
    siteName: 'Agenlate',
    type: 'website',
  },
}

// Dark only, matching the pages: the browser's own chrome on phones takes this
// colour, and a light bar above a dark page reads as a rendering fault.
export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#0a0a0a',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${poppins.variable} ${jakarta.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: domGuardScript }} />
      </head>
      <body className="font-sans antialiased overflow-hidden">
        <WakeBackend />
        <AuthProvider>{children}</AuthProvider>
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
