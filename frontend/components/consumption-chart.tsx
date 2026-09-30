'use client'

/**
 * Spending per day.
 *
 * The series arrives with quiet days already filled in as zero, so the shape
 * is honest: a fortnight of nothing looks like a fortnight of nothing rather
 * than a straight line drawn between the two days either side of it.
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DailyUsage } from '@/lib/agenlate'
import { formatUsd } from '@/lib/format'

export function ConsumptionChart({ series }: { series: DailyUsage[] }) {
  const data = series.map((point) => ({
    label: new Date(point.day).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    }),
    value: point.cost_usd,
    requests: point.requests,
  }))

  const spentAnything = data.some((point) => point.value > 0)

  return (
    <div className="rounded-lg border border-[#262629] bg-[#0A0A0A] p-3">
      {!spentAnything && (
        <p className="px-2 pb-2 pt-1 text-[11.5px] font-light text-[#7d7d82]">
          Nothing spent in this window yet.
        </p>
      )}
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: -4 }}>
          <defs>
            <linearGradient id="yellowGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#FFF41F" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#FFF41F" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f1f23" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: '#7d7d82' }}
            axisLine={{ stroke: '#262629' }}
            tickLine={false}
            // A month of daily labels overlaps into illegibility; showing
            // every few keeps the axis readable at any window length.
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#7d7d82' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(value) => formatUsd(Number(value ?? 0))}
            // Wide enough for "$0.0075": narrower and the dollar sign is cut off.
            width={68}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#141414',
              border: '1px solid #262629',
              borderRadius: '8px',
              fontSize: '12px',
              color: '#ffffff',
            }}
            itemStyle={{ color: '#FFF41F' }}
            labelStyle={{ fontWeight: 600, color: '#ffffff' }}
            formatter={(value, _name, entry) => {
              const requests = Number(entry?.payload?.requests ?? 0)
              return [
                `${formatUsd(Number(value ?? 0))} · ${requests} request${
                  requests === 1 ? '' : 's'
                }`,
                'Spent',
              ]
            }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#FFF41F"
            strokeWidth={2}
            fill="url(#yellowGradient)"
            // A dot on each day with spending. Without one, a single active
            // day — the usual case for a new account — is a line drawn to the
            // chart's edge that nobody can see.
            dot={(props: {
              cx?: number
              cy?: number
              index?: number
              payload?: { value?: number }
            }) =>
              // The day's own figure, not the dot's `value`, which an area
              // series can report as a [base, top] pair that is always truthy.
              props.payload?.value ? (
                <circle
                  key={props.index}
                  cx={props.cx}
                  cy={props.cy}
                  r={3.5}
                  fill="#FFF41F"
                  stroke="#0A0A0A"
                  strokeWidth={1}
                />
              ) : (
                <g key={props.index} />
              )
            }
            activeDot={{ r: 5, fill: '#FFF41F', stroke: '#111111', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
