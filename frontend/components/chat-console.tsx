'use client'

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  agents,
  conversation,
  streamingMessage,
  type ChatItem,
} from '@/lib/agenlate-data'
import { ArrowRight, ChevronDown, Cpu, Eye } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

function agentById(id: string) {
  return agents.find((a) => a.id === id)!
}

function SystemLine({ item }: { item: Extract<ChatItem, { kind: 'system' }> }) {
  return (
    <div className="my-1 flex items-center gap-3">
      <span className="h-px flex-1 bg-[#16161a]" />
      <div className="flex items-center gap-2 rounded-full border border-[#16161a] bg-[#1a1a1a] px-3 py-1 text-[11px] font-light text-[#7d7d82]">
        <Cpu className="size-3 text-[#7d7d82]" />
        <span className="font-medium text-[#d4d4d8]">[{item.from}]</span>
        <ArrowRight className="size-3 text-[#7d7d82]" />
        <span>{item.action}</span>
        <ArrowRight className="size-3 text-[#7d7d82]" />
        <span>
          Ceding turn to:{' '}
          <span className="font-medium text-[#d4d4d8]">{item.cedeTo}</span>
        </span>
      </div>
      <span className="h-px flex-1 bg-[#16161a]" />
    </div>
  )
}

function MessageBlock({
  agentId,
  cost,
  time,
  children,
}: {
  agentId: string
  cost: string
  time: string
  children: React.ReactNode
}) {
  const agent = agentById(agentId)
  return (
    <div className="flex gap-3">
      <div
        className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg text-[12px] font-semibold text-primary-foreground"
        style={{ backgroundColor: agent.color }}
        aria-hidden
      >
        {agent.initials}
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex items-start justify-between gap-3">
          <div className="flex flex-col leading-tight">
            <span className="text-[14px] font-semibold text-white">{agent.name}</span>
            <span className="text-[11px] font-medium uppercase tracking-wide text-[#7d7d82]">
              {agent.role}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="text-[11px] font-light text-[#7d7d82]">{time}</span>
            <span className="rounded-md border border-[#16161a] bg-[#1a1a1a] px-2 py-0.5 font-mono text-[10px] font-light tabular-nums text-[#d4d4d8]">
              {cost}
            </span>
          </div>
        </div>
        <p className="text-[13.5px] font-light leading-relaxed text-[#8e8e93]">
          {children}
        </p>
      </div>
    </div>
  )
}

function StreamingMessage() {
  const { fullText } = streamingMessage
  const [shown, setShown] = useState('')

  useEffect(() => {
    let i = 0
    const interval = setInterval(() => {
      i += 2
      setShown(fullText.slice(0, i))
      if (i >= fullText.length) clearInterval(interval)
    }, 24)
    return () => clearInterval(interval)
  }, [fullText])

  return (
    <MessageBlock
      agentId={streamingMessage.agentId}
      cost={streamingMessage.cost}
      time={streamingMessage.time}
    >
      {shown}
      <span className="blink-cursor" aria-hidden />
    </MessageBlock>
  )
}

export function ChatConsole({ empty }: { empty?: boolean }) {
  const [streamOpen, setStreamOpen] = useState(true)

  const data = empty ? [] : conversation
  const rendered = useMemo(
    () =>
      data.map((item) =>
        item.kind === 'system' ? (
          <SystemLine key={item.id} item={item} />
        ) : (
          <MessageBlock key={item.id} agentId={item.agentId} cost={item.cost} time={item.time}>
            {item.body}
          </MessageBlock>
        ),
      ),
    [],
  )

  return (
    <section className="flex h-full w-[420px] shrink-0 flex-col border-l border-[#16161a] bg-panel">

      {/* Streaming feed */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="scrollbar-thin flex-1 overflow-y-auto">
          <Collapsible open={streamOpen} onOpenChange={setStreamOpen}>
            <div
              className={`border border-[#16161a] transition-colors ${
                streamOpen
                  ? 'bg-[#141414] dark:bg-[#141414]'
                  : 'bg-[#141414] dark:bg-[#141414]'
              }`}
            >
              <CollapsibleTrigger className="group flex w-full items-center justify-between border-b border-[#16161a] px-5 py-3 text-left transition-colors hover:bg-[#141414] dark:hover:bg-secondary/30">
                <span className="flex items-center gap-2">
                  <Eye className="size-3.5 text-[#7d7d82]" />
                  <span className="text-[12px] font-semibold uppercase tracking-wide text-white">
                    LIVE ORCHESTRATION
                  </span>
                </span>
                <div className="flex items-center gap-2">
                  {streamOpen && (
                    <span className="flex items-center gap-1.5">
                      <span className="size-1.5 rounded-full bg-green-500 pulse-dot" aria-hidden />
                      <span className="text-[10px] font-medium uppercase tracking-wider text-[#d4d4d8]">
                        Streaming
                      </span>
                    </span>
                  )}
                  <ChevronDown
                    className={`size-4 text-muted-foreground transition-transform ${
                      streamOpen ? 'rotate-180' : ''
                    }`}
                  />
                </div>
              </CollapsibleTrigger>

              <CollapsibleContent>
                <div className="flex flex-col gap-4 border-t border-[#16161a] px-4 py-5">
                  {rendered}
                  {!empty && <StreamingMessage />}
                </div>
              </CollapsibleContent>
            </div>
            </Collapsible>

          
        </div>
      </div>
    </section>
  )
}
