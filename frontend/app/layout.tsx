import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Poppins } from 'next/font/google'
import './globals.css'

/**
 * Blocking, pre-paint theme bootstrap.
 * Light mode is the DEFAULT: <html> simply has no theme class. The Bunker dark
 * theme is restored by adding `dark` to <html> here — before the first paint —
 * so the operator never sees a flash of the wrong theme. Keep the storage key
 * and class name in sync with `components/theme-toggle.tsx`.
 */
const themeInitScript = `(function(){try{var stored=window.localStorage.getItem('agenlate-theme');var dark=stored==='dark';var root=document.documentElement;root.classList.toggle('dark',dark);root.style.colorScheme=dark?'dark':'light'}catch(e){}})()`

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
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
