import { Analytics } from '@vercel/analytics/next'

import { AuthProvider } from '@/components/auth-provider'
import { WakeBackend } from '@/components/wake-backend'
import type { Metadata, Viewport } from 'next'
import { Poppins } from 'next/font/google'
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

export const metadata: Metadata = {
  title: 'Agenlate — AI Multi-Agent Platform',
  description:
    'Agenlate is a premium multi-agent orchestration console with live streaming, transparent supervisor routing, and real-time budget tracking.',
  generator: 'v0.app',
}

export const viewport: Viewport = {
  colorScheme: 'light dark',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f9f9f9' },
    { media: '(prefers-color-scheme: dark)', color: '#0a0a0a' },
  ],
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={poppins.variable} suppressHydrationWarning>
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
