/**
 * agenlate.com — the public front door.
 *
 * For someone who has never heard of Agenlate: what it is, how it works, and a
 * way in. The Beta is invite-only, so the main action is joining the waitlist;
 * people with a code go straight to sign-up, and people already signed in are
 * offered their workspace.
 *
 * Every claim here describes something the product does today. A landing page
 * that promises features the app does not have loses the Beta users it was
 * built to attract on their first visit.
 *
 * Rendered on the server except for the two interactive pieces, so it is fast
 * and readable by search engines and link previews.
 */

import Link from 'next/link'
import {
  Eye,
  KeyRound,
  MessageSquareText,
  Receipt,
  ShieldCheck,
  Sparkles,
  Target,
  Users,
} from 'lucide-react'

import { AgenlateLogo, AgenlateMark } from '@/components/brand'
import { AuthActions } from '@/components/landing/auth-actions'
import { WaitlistForm } from '@/components/landing/waitlist-form'

const HEADING = { fontFamily: 'var(--font-jakarta), ui-sans-serif, sans-serif' }

export default function LandingPage() {
  return (
    // The app's body does not scroll — every signed-in screen scrolls inside
    // its own panels — so this page is its own scroll container.
    <div
      className="h-dvh overflow-y-auto scroll-smooth bg-[#0A0A0A] text-white"
      style={HEADING}
    >
      <Header />
      <main>
        <Hero />
        <HowItWorks />
        <Principles />
        <FinalCall />
      </main>
      <Footer />
    </div>
  )
}

function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#0A0A0A]/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
        <Link href="/" className="flex items-center gap-2.5" aria-label="Agenlate home">
          <AgenlateLogo />
          <span className="hidden rounded-md border border-[#FFF41F]/40 bg-[#FFF41F]/10 px-1.5 py-0.5 text-[9px] font-bold tracking-wide text-[#FFF41F] sm:inline">
            BETA
          </span>
        </Link>
        <nav className="hidden items-center gap-7 text-[13px] font-medium text-[#a1a1aa] md:flex">
          <a href="#how" className="transition-colors hover:text-white">
            How it works
          </a>
          <a href="#principles" className="transition-colors hover:text-white">
            Why Agenlate
          </a>
          <a href="#join" className="transition-colors hover:text-white">
            Join the Beta
          </a>
        </nav>
        <AuthActions />
      </div>
    </header>
  )
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* The brand kit's construction circles, as quiet background light. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-40 -top-40 size-[640px] rounded-full bg-[#FFF41F]/[0.07] blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-60 top-60 size-[520px] rounded-full bg-cyan-400/[0.05] blur-3xl"
      />

      <div className="relative mx-auto grid max-w-6xl items-center gap-14 px-5 pb-20 pt-16 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:pb-28 lg:pt-24">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[12px] font-medium text-[#d4d4d8]">
            <span className="size-1.5 rounded-full bg-[#FFF41F]" aria-hidden />
            Invite-only Beta, now open
          </p>
          <h1 className="mt-6 text-[40px] font-extrabold leading-[1.05] tracking-tight sm:text-[56px]">
            Describe the team.
            <br />
            <span className="text-[#FFF41F]">Watch it work.</span>
          </h1>
          <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-[#a1a1aa]">
            Agenlate turns plain words into a team of AI agents. Say what you need,
            and it helps you design each worker. A Supervisor hands out the work,
            and you watch every step as it happens.
          </p>

          <div className="mt-9 max-w-lg" id="join-top">
            <WaitlistForm source="landing" />
            <p className="mt-3 text-[13px] text-[#7d7d82]">
              Already have an invite code?{' '}
              <Link
                href="/login?mode=signup"
                className="font-semibold text-[#FFF41F] underline-offset-4 hover:underline"
              >
                Create your account
              </Link>
            </p>
          </div>
        </div>

        <RoomPreview />
      </div>
    </section>
  )
}

/**
 * What a room looks like mid-run, drawn rather than screenshotted so it stays
 * crisp and on-brand. The exchange mirrors how a real run proceeds: the
 * Supervisor decides, hands a turn to an agent, and stops to ask the owner
 * when it needs something only they know.
 */
function RoomPreview() {
  return (
    <div className="relative" aria-label="Example of a room at work" role="img">
      <div className="rounded-2xl border border-white/[0.08] bg-[#111113] p-2 shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between rounded-t-xl border-b border-white/[0.06] bg-[#141414] px-4 py-3">
          <span className="text-[11px] font-bold uppercase tracking-wider text-white">
            Live orchestration
          </span>
          <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#d4d4d8]">
            <span className="size-1.5 animate-pulse rounded-full bg-green-500" />
            Running · $0.004
          </span>
        </div>

        <div className="space-y-4 p-4">
          <PreviewMessage who="Supervisor" role="Orchestration" supervisor>
            Research comes first. Handing the turn to the Researcher.
          </PreviewMessage>
          <PreviewMessage who="Researcher" role="Finds and checks sources" initials="RE" color="#60a5fa">
            Found three recent reports on cold-brew demand, with sources.
          </PreviewMessage>
          <PreviewMessage who="Writer" role="Drafts clear copy" initials="WR" color="#34d399">
            Drafted a 500-word post from those findings.
          </PreviewMessage>

          <div className="rounded-xl border border-[#FFF41F]/25 bg-[#FFF41F]/[0.05] px-3.5 py-3">
            <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-[#FFF41F]">
              <MessageSquareText className="size-3.5" />
              The Supervisor needs your input
            </p>
            <p className="mt-1 text-[13px] leading-relaxed text-[#e4e4e7]">
              Should the post name the three brands, or keep them anonymous?
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function PreviewMessage({
  who,
  role,
  initials,
  color,
  supervisor,
  children,
}: {
  who: string
  role: string
  initials?: string
  color?: string
  supervisor?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="flex gap-3">
      {supervisor ? (
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[#FFF41F] text-[#0A0A0A]">
          <AgenlateMark className="w-[62%]" title={null} />
        </span>
      ) : (
        <span
          className="flex size-8 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold text-[#0A0A0A]"
          style={{ backgroundColor: color }}
        >
          {initials}
        </span>
      )}
      <div className="min-w-0">
        <p className="text-[13px] font-bold text-white">
          {who}{' '}
          <span className="ml-1 text-[10px] font-semibold uppercase tracking-wide text-[#7d7d82]">
            {role}
          </span>
        </p>
        <p className="mt-0.5 text-[13px] leading-relaxed text-[#a1a1aa]">{children}</p>
      </div>
    </div>
  )
}

const STEPS = [
  {
    icon: Users,
    title: 'Describe your agents',
    body:
      'Tell the builder what each worker should do, in your own words. It asks what it needs to know, writes their instructions, and you decide whether to keep them.',
  },
  {
    icon: Target,
    title: 'Set the objective',
    body:
      'Say what the room should achieve. The writing helper turns it into a clear brief, with a finish line the team can recognise.',
  },
  {
    icon: Eye,
    title: 'Watch them work',
    body:
      'A Supervisor decides who acts next and when the job is done. When it needs something only you know, it stops and asks.',
  },
]

function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-20 border-t border-white/[0.06] bg-[#0c0c0d]">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-28">
        <SectionHeading
          eyebrow="How it works"
          title="From a sentence to a working team"
          lead="No prompts to write and nothing to wire together. Three steps, all in plain language."
        />
        <ol className="mt-14 grid gap-5 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li
              key={step.title}
              className="relative rounded-2xl border border-white/[0.07] bg-[#141414] p-6"
            >
              <span className="absolute right-5 top-5 text-[40px] font-extrabold leading-none text-white/[0.05]">
                {index + 1}
              </span>
              <span className="flex size-10 items-center justify-center rounded-xl bg-[#FFF41F]/10 text-[#FFF41F]">
                <step.icon className="size-5" strokeWidth={2} />
              </span>
              <h3 className="mt-5 text-[18px] font-bold">{step.title}</h3>
              <p className="mt-2 text-[14px] leading-relaxed text-[#a1a1aa]">{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

const PRINCIPLES = [
  {
    icon: Sparkles,
    title: 'Plain language, start to finish',
    body:
      'You never face a blank box labelled "system prompt". The builder writes your agents and the helper writes your objective — you just say what you want.',
  },
  {
    icon: Receipt,
    title: 'Every cent visible',
    body:
      'See what each step cost as it happens, what every room has spent, and a log of every model call your rooms make. No estimates, no surprises.',
  },
  {
    icon: KeyRound,
    title: 'Your key, your credit',
    body:
      'Agenlate runs on your own OpenRouter key, so you pay the model provider directly. We never hold your credit or take a cut, and your key is stored only in your browser — never saved on our servers.',
  },
  {
    icon: ShieldCheck,
    title: 'You stay in charge',
    body:
      'Pause any room without losing it. Every run stops at a spending cap. And the Supervisor asks when it is unsure, rather than guessing with your money.',
  },
]

function Principles() {
  return (
    <section id="principles" className="scroll-mt-20 border-t border-white/[0.06]">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-28">
        <SectionHeading
          eyebrow="Why Agenlate"
          title="Built so you can trust what the team is doing"
          lead="Multi-agent systems are powerful and usually opaque. Agenlate shows you every decision and every cost."
        />
        <div className="mt-14 grid gap-5 sm:grid-cols-2">
          {PRINCIPLES.map((item) => (
            <div
              key={item.title}
              className="flex gap-4 rounded-2xl border border-white/[0.07] bg-[#141414] p-6"
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-white/[0.04] text-[#FFF41F]">
                <item.icon className="size-5" strokeWidth={2} />
              </span>
              <div>
                <h3 className="text-[17px] font-bold">{item.title}</h3>
                <p className="mt-1.5 text-[14px] leading-relaxed text-[#a1a1aa]">{item.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function FinalCall() {
  return (
    <section id="join" className="scroll-mt-20 border-t border-white/[0.06]">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-28">
        <div className="relative overflow-hidden rounded-3xl border border-[#FFF41F]/20 bg-[#121212] px-6 py-14 text-center sm:px-12">
          <div
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-0 size-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#FFF41F]/[0.08] blur-3xl"
          />
          <span className="relative mx-auto flex size-14 items-center justify-center rounded-2xl bg-[#FFF41F] text-[#0A0A0A]">
            <AgenlateMark className="w-[60%]" title={null} />
          </span>
          <h2 className="relative mt-6 text-[30px] font-extrabold tracking-tight sm:text-[40px]">
            Join the Beta
          </h2>
          <p className="relative mx-auto mt-3 max-w-lg text-[16px] leading-relaxed text-[#a1a1aa]">
            We are letting people in a few at a time. Leave your email and we will send
            you an invite when a place opens up.
          </p>
          <div className="relative mx-auto mt-8 max-w-lg text-left">
            <WaitlistForm source="landing-footer" />
          </div>
        </div>
      </div>
    </section>
  )
}

function SectionHeading({ eyebrow, title, lead }: { eyebrow: string; title: string; lead: string }) {
  return (
    <div className="max-w-2xl">
      <p className="text-[12px] font-bold uppercase tracking-[0.14em] text-[#FFF41F]">{eyebrow}</p>
      <h2 className="mt-3 text-[30px] font-extrabold leading-tight tracking-tight sm:text-[40px]">
        {title}
      </h2>
      <p className="mt-4 text-[16px] leading-relaxed text-[#a1a1aa]">{lead}</p>
    </div>
  )
}

function Footer() {
  return (
    <footer className="border-t border-white/[0.06]">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-5 py-8 text-[13px] text-[#7d7d82] sm:flex-row sm:px-8">
        <AgenlateLogo />
        <p>© {new Date().getFullYear()} Agenlate. All rights reserved.</p>
        <Link href="/login" className="font-medium transition-colors hover:text-white">
          Sign in
        </Link>
      </div>
    </footer>
  )
}
