'use client'

/**
 * Renders what a model wrote, formatted.
 *
 * Models write Markdown whether asked to or not — headings, lists, bold,
 * tables. Shown as plain text that is a page of pound signs and asterisks,
 * which is how the work looked before this and part of why a tester could not
 * tell where the finished result was.
 *
 * Raw HTML in the text is not rendered. react-markdown ignores it by default,
 * and that default is the point: this text comes from a model, which can be
 * steered by whatever it read on the web, so it must not be able to put
 * markup of its own into the page.
 */

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** `reading` for the full-width result; `compact` for the narrow transcript. */
type Size = 'reading' | 'compact'

const SIZES: Record<Size, { text: string; h1: string; h2: string; h3: string; gap: string }> = {
  reading: {
    text: 'text-[15px] leading-[1.7]',
    h1: 'text-[24px]',
    h2: 'text-[19px]',
    h3: 'text-[16px]',
    gap: 'space-y-4',
  },
  compact: {
    text: 'text-[13.5px] leading-relaxed',
    h1: 'text-[16px]',
    h2: 'text-[15px]',
    h3: 'text-[14px]',
    gap: 'space-y-2.5',
  },
}

export function Markdown({
  children,
  size = 'reading',
  className = '',
}: {
  children: string
  size?: Size
  className?: string
}) {
  const s = SIZES[size]
  const heading = 'font-semibold tracking-tight text-white'

  return (
    <div className={`${s.text} ${s.gap} break-words font-light text-[#c4c4c8] ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className={`${heading} ${s.h1} mt-2`}>{children}</h1>,
          h2: ({ children }) => <h2 className={`${heading} ${s.h2} mt-2`}>{children}</h2>,
          h3: ({ children }) => <h3 className={`${heading} ${s.h3} mt-1`}>{children}</h3>,
          h4: ({ children }) => <h4 className={`${heading} mt-1`}>{children}</h4>,
          p: ({ children }) => <p>{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
          li: ({ children }) => <li className="pl-0.5">{children}</li>,
          a: ({ children, href }) => (
            // New tab, and no opener or referrer: a link an agent found on the
            // web should not be handed a reference back to this page.
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="font-normal text-[#FFF41F] underline decoration-[#FFF41F]/40 underline-offset-2 hover:decoration-[#FFF41F]"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-[#FFF41F]/40 pl-3.5 text-[#a1a1aa]">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="border-[#262629]" />,
          code: ({ children, className }) =>
            className ? (
              // A fenced block: the class carries the language.
              <code className="font-mono text-[12.5px]">{children}</code>
            ) : (
              <code className="rounded bg-[#1f1f23] px-1.5 py-0.5 font-mono text-[0.88em] text-[#e4e4e7]">
                {children}
              </code>
            ),
          pre: ({ children }) => (
            // A fenced block with no language carries no class, so its code
            // element gets the inline styling above; undo that inside a block.
            <pre className="overflow-x-auto rounded-lg border border-[#16161a] bg-[#0f0f0f] px-3.5 py-3 text-[#e4e4e7] [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-[12.5px]">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto rounded-lg border border-[#16161a]">
              <table className="w-full border-collapse text-left text-[0.92em]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-[#262629] bg-[#141414] px-3 py-2 font-semibold text-white">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-[#16161a] px-3 py-2 align-top">{children}</td>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
