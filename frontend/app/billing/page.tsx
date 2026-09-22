'use client'

import { useState } from 'react'
import { TopNavbar } from '@/components/top-navbar'
import { LobbySidebar } from '@/components/lobby-sidebar'
import { ConsumptionChart } from '@/components/consumption-chart'
import { Wallet, CreditCard, CalendarDays, ChevronDown } from 'lucide-react'

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']
const DAY_NM = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
const Y = 2026
const M = 6

function dim(y: number, m: number): number { return new Date(y, m + 1, 0).getDate() }
function fdm(y: number, m: number): number { return new Date(y, m, 1).getDay() }

export default function BillingPage() {
  const [fromOpen, setFromOpen] = useState(false)
  const [toOpen, setToOpen] = useState(false)
  const [startDay, setStartDay] = useState(20)
  const [endDay, setEndDay] = useState(18)
  const totalDays = dim(Y, M)
  const firstDay = fdm(Y, M)

  function hdl(day: number, mode: 'from' | 'to') {
    if (mode === 'from') { setStartDay(day); setFromOpen(false) }
    else { setEndDay(day); setToOpen(false) }
  }

  function btnCls(day: number, mode: 'from' | 'to'): string {
    const activeDay = mode === 'from' ? startDay : endDay
    if (day === activeDay && activeDay !== 0) return 'flex items-center justify-center rounded-md py-1.5 text-[11.5px] bg-[#FFF41F] font-semibold text-[#111111]'
    return 'flex items-center justify-center rounded-md py-1.5 text-[11.5px] text-[#52525B] hover:bg-[#EBEBEB] dark:text-[#7d7d82] dark:hover:bg-[#1a1a1a]'
  }

  return (
    <div className="flex h-screen max-h-screen w-full flex-col overflow-hidden bg-[#0a0a0a] text-foreground">
      <TopNavbar /><div className="flex min-h-0 flex-1 pt-[56px]">
        <div className="hidden md:flex"><LobbySidebar /></div>
        <div className="flex min-w-0 flex-1 flex-col gap-6 overflow-y-auto pl-16 pr-6 pt-12 pb-6">
          <div className="w-full max-w-3xl">
            <div className="mb-10">
              <h1 className="flex items-center gap-2.5 text-[20px] font-semibold tracking-tight text-[#111111] dark:text-white">
                <CreditCard className="size-5 text-[#7A6F00] dark:text-[#FFF41F]" strokeWidth={1.5} />Billing</h1>
              <p className="mt-1.5 text-[13px] font-light leading-relaxed text-[#52525B] dark:text-[#7d7d82]">Monitor your active multi-agent cloud expenditure, aggregate credit consumption, and daily compute analytics in real-time.</p>
            </div>
<div className="mb-6 rounded-xl bg-[#141414] px-5 pb-6 pt-5 transition-all dark:bg-[#141414]">
              <div className="mb-3 flex items-center gap-2">
                <Wallet className="size-4 text-[#7d7d82]" strokeWidth={1.5} />
                <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[#7d7d82]">Fund Balance</h3></div>
              <div className="flex items-baseline gap-3">
                <span className="text-[36px] font-semibold tracking-tight text-[#111111] dark:text-white">$48.20</span>
                <span className="text-[15px] font-light text-[#a1a1aa]">USD</span>
                <button type="button" className="ml-4 inline-flex items-center gap-2 rounded-md bg-[#FFF41F] px-4 py-2 text-[13px] font-semibold text-[#111111] transition-all hover:brightness-95 dark:text-[#0A0A0A]">Top Up Credits</button></div></div>

            <div className="mb-4 flex items-center gap-3 px-1">
              <button type="button" onClick={() => { setToOpen(false); setFromOpen(!fromOpen); }} className="inline-flex items-center gap-2 rounded-md border border-[#16161a] bg-[#141414] px-3 py-2 text-[12px] font-light text-[#7d7d82] transition-colors hover:border-[#7A6F00]/40 dark:border-[#16161a] dark:bg-[#141414] dark:text-[#7d7d82] dark:hover:border-[#FFF41F]/50">
                <CalendarDays className="size-3.5 text-[#7A6F00] dark:text-[#FFF41F]" strokeWidth={1.5} />
                <span className="text-[11px] font-medium text-[#7d7d82]">From: {MONTHS[M]} {startDay}, {Y}</span>
                <ChevronDown className={'size-3 text-[#71717A] transition-transform ' + (fromOpen ? 'rotate-180' : '')} strokeWidth={1.5} /></button>
              <button type="button" onClick={() => { setFromOpen(false); setToOpen(!toOpen); }} className="inline-flex items-center gap-2 rounded-md border border-[#16161a] bg-[#141414] px-3 py-2 text-[12px] font-light text-[#7d7d82] transition-colors hover:border-[#7A6F00]/40 dark:border-[#16161a] dark:bg-[#141414] dark:text-[#7d7d82] dark:hover:border-[#FFF41F]/50">
                <CalendarDays className="size-3.5 text-[#7A6F00] dark:text-[#FFF41F]" strokeWidth={1.5} />
                <span className="text-[11px] font-medium text-[#7d7d82]">To: {MONTHS[M]} {endDay || startDay}, {Y}</span>
                <ChevronDown className={'size-3 text-[#71717A] transition-transform ' + (toOpen ? 'rotate-180' : '')} strokeWidth={1.5} /></button>
              <div className="ml-2 flex items-center gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-[#7d7d82]">Spent</span>
                <span className="font-mono text-[14px] font-semibold tabular-nums text-[#111111] dark:text-white">$8.50</span>
                <span className="text-[9px] text-[#a1a1aa]">USD</span></div></div>

            {fromOpen && (
              <div className="relative mb-4 px-1"><div className="absolute left-4 -top-2 z-50 w-72 rounded-lg border border-[#16161a] bg-[#141414] p-3 dark:border-[#16161a] dark:bg-[#141414]">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[13px] font-semibold text-[#111111] dark:text-white">{MONTHS[M]} {Y}</span></div>
                  <div className="mb-1 grid grid-cols-7 gap-0.5">
                    {DAY_NM.map((d) => <div key={d} className="py-1 text-center text-[9px] font-medium uppercase tracking-wider text-[#52525B] dark:text-[#7d7d82]">{d}</div>)}</div>
                  <div className="grid grid-cols-7 gap-0.5">
                    {Array.from({ length: firstDay }).map((_, i) => <div key={i} className="invisible" />)}
                    {Array.from({ length: totalDays }, (_, i) => i + 1).map((day) => (
                      <button key={day} type="button" onClick={() => hdl(day, 'from')} className={btnCls(day, 'from')}>{day}</button>))}</div></div></div>)}
            {toOpen && (
              <div className="relative mb-4 px-1"><div className="absolute left-4 -top-2 z-50 w-72 rounded-lg border border-[#16161a] bg-[#141414] p-3 dark:border-[#16161a] dark:bg-[#141414]">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[13px] font-semibold text-[#111111] dark:text-white">{MONTHS[M]} {Y}</span></div>
                  <div className="mb-1 grid grid-cols-7 gap-0.5">
                    {DAY_NM.map((d) => <div key={d} className="py-1 text-center text-[9px] font-medium uppercase tracking-wider text-[#52525B] dark:text-[#7d7d82]">{d}</div>)}</div>
                  <div className="grid grid-cols-7 gap-0.5">
                    {Array.from({ length: firstDay }).map((_, i) => <div key={i} className="invisible" />)}
                    {Array.from({ length: totalDays }, (_, i) => i + 1).map((day) => (
                      <button key={day} type="button" onClick={() => hdl(day, 'to')} className={btnCls(day, 'to')}>{day}</button>))}</div></div></div>)}
<div className="mb-6">
              <ConsumptionChart />
            </div>

            <div className="mb-6 px-1">
              <h3 className="mb-4 text-[12px] font-semibold uppercase tracking-wide text-[#52525B] dark:text-[#7d7d82]">Consumption Audit Log</h3>
              <div className="max-h-[280px] overflow-y-auto overflow-x-auto scrollbar-thin rounded-lg border border-[#16161a]">
                <table className="w-full text-left text-[12px]">
                  <thead>
                    <tr className="border-b border-[#16161a] text-[10px] font-medium uppercase tracking-wider text-[#52525B] dark:text-[#7d7d82]">
                      <th className="sticky top-0 bg-white px-1 pb-2.5 pt-2.5 font-medium dark:bg-[#0A0A0A]">USD Spent</th>
                      <th className="sticky top-0 bg-white px-1 pb-2.5 pt-2.5 font-medium dark:bg-[#0A0A0A]">Workspace</th>
                      <th className="sticky top-0 bg-white px-1 pb-2.5 pt-2.5 font-medium dark:bg-[#0A0A0A]">Agent Name</th>
                      <th className="sticky top-0 bg-white px-1 pb-2.5 pt-2.5 font-medium dark:bg-[#0A0A0A]">Time</th>
                      <th className="sticky top-0 bg-white px-1 pb-2.5 pt-2.5 font-medium dark:bg-[#0A0A0A]">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { usd: '$0.421', room: 'Production Deploy', agent: 'Orquestador', time: '14:32:05', date: '2026-06-25' },
                      { usd: '$1.204', room: 'Production Deploy', agent: 'Code Auditor', time: '14:33:12', date: '2026-06-25' },
                      { usd: '$0.087', room: 'Production Deploy', agent: 'Infra Engineer', time: '14:34:48', date: '2026-06-25' },
                      { usd: '$0.613', room: 'Smart Contract', agent: 'Security Analyst', time: '09:15:22', date: '2026-06-23' },
                    ].map((row, i) => (
                      <tr key={i} className="border-b border-[#16161a] transition-colors hover:bg-black/5 dark:border-[#16161a] dark:hover:bg-white/5">
                        <td className="px-1 py-3 font-mono text-[13px] font-semibold tabular-nums text-[#111111] dark:text-white">{row.usd}</td>
                        <td className="px-1 py-3 text-[#111111] dark:text-white">{row.room}</td>
                        <td className="px-1 py-3 text-[#111111] dark:text-white">{row.agent}</td>
                        <td className="px-1 py-3 font-mono text-[11px] text-[#52525B] dark:text-[#7d7d82]">{row.time}</td>
                        <td className="px-1 py-3 font-mono text-[11px] text-[#52525B] dark:text-[#7d7d82]">{row.date}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
