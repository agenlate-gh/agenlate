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
  title: 'Agenlate — Describe the team. Watch it work.',
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
      </head>
      <body className="font-sans antialiased overflow-hidden">
        <WakeBackend />
        <AuthProvider>{children}</AuthProvider>
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
