'use client'

/**
 * Asking Beta users what they want.
 *
 * Two questions everyone is asked — what they would automate, and which tools
 * they would connect — and a box for anything else. Each answer is stored
 * under its question, so the answers can be read and counted per question.
 * Any one box is enough to send.
 *
 * The button sits in the top bar rather than in the account menu: feedback
 * nobody can find is feedback nobody sends.
 */

import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { Check, Loader2, MessageSquareText, X } from 'lucide-react'

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { feedback } from '@/lib/agenlate'
import { ApiError } from '@/lib/api'

const QUESTIONS = [
  {
    key: 'automate',
    label: 'What would you like your agents to do for you?',
    placeholder: 'e.g. a weekly report on my competitors, replies to customer emails…',
  },
  {
    key: 'connect',
    label: 'Which tools would you like them to connect to?',
    placeholder: 'e.g. Gmail, WhatsApp, Notion, Google Sheets…',
  },
  {
    key: 'general',
    label: 'Anything else? Ideas, problems, what you liked.',
    placeholder: 'Optional',
  },
] as const

type Answers = Record<(typeof QUESTIONS)[number]['key'], string>

const EMPTY: Answers = { automate: '', connect: '', general: '' }

export function FeedbackButton() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const [answers, setAnswers] = useState<Answers>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  const hasAnswer = Object.values(answers).some((value) => value.trim())

  function openChange(next: boolean) {
    setOpen(next)
    if (!next && sent) {
      // A fresh form next time; a half-written one is kept.
      setAnswers(EMPTY)
      setSent(false)
    }
  }

  async function send(event: React.FormEvent) {
    event.preventDefault()
    if (!hasAnswer || busy) return
    setBusy(true)
    setError(null)
    try {
      await feedback.send({ ...answers, page: pathname })
      setSent(true)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not send. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[12.5px] font-medium text-[#52525B] transition-colors hover:text-[#111111] dark:text-[#7d7d82] dark:hover:text-white"
      >
        <MessageSquareText className="size-4" strokeWidth={1.5} />
        <span className="hidden sm:inline">Feedback</span>
      </button>

      <Dialog open={open} onOpenChange={openChange}>
        <DialogContent className="max-w-lg gap-0 p-0">
          <header className="flex items-start justify-between gap-4 border-b border-[#16161a] px-6 py-4">
            <div>
              <DialogTitle className="text-[17px]">
                {sent ? 'Thank you' : 'Help us shape Agenlate'}
              </DialogTitle>
              <DialogDescription className="mt-0.5 text-[12.5px]">
                {sent
                  ? 'We read every answer. It decides what we build next.'
                  : 'Answer any of these. One is enough.'}
              </DialogDescription>
            </div>
            <DialogClose
              aria-label="Close feedback"
              className="flex size-8 items-center justify-center rounded-md text-[#7d7d82] transition-colors hover:bg-[#1a1a1a] hover:text-white"
            >
              <X className="size-4" />
            </DialogClose>
          </header>

          {sent ? (
            <div className="flex flex-col items-center px-6 py-10 text-center">
              <span className="flex size-11 items-center justify-center rounded-xl bg-[#FFF41F]/10 text-[#FFF41F]">
                <Check className="size-5" strokeWidth={2} />
              </span>
              <DialogClose className="mt-6 rounded-lg bg-[#FFF41F] px-4 py-2 text-[13px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95">
                Back to Agenlate
              </DialogClose>
            </div>
          ) : (
            <form onSubmit={send} className="flex flex-col gap-4 px-6 py-5">
              {QUESTIONS.map((question) => (
                <label key={question.key} className="flex flex-col gap-1.5">
                  <span className="text-[12.5px] font-medium text-white">{question.label}</span>
                  <textarea
                    value={answers[question.key]}
                    onChange={(event) =>
                      setAnswers((prev) => ({ ...prev, [question.key]: event.target.value }))
                    }
                    rows={2}
                    maxLength={2000}
                    placeholder={question.placeholder}
                    className="resize-none rounded-lg border border-[#16161a] bg-[#141414] px-3.5 py-2.5 text-[13px] font-light leading-relaxed text-white outline-none transition-colors placeholder:text-[#52525B] focus:border-[#FFF41F]/50"
                  />
                </label>
              ))}

              {error && (
                <p role="alert" className="text-[12px] font-light text-[#FCA5A5]">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={!hasAnswer || busy}
                className="mt-1 inline-flex items-center justify-center gap-2 rounded-lg bg-[#FFF41F] px-4 py-2.5 text-[13px] font-semibold text-[#0A0A0A] transition-all hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy && <Loader2 className="size-3.5 animate-spin" />}
                <span>Send</span>
              </button>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
