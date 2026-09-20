'use client'

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

const chartData = [
  { label: 'Mon', value: 1.2 },
  { label: 'Tue', value: 2.1 },
  { label: 'Wed', value: 1.8 },
  { label: 'Thu', value: 2.4 },
  { label: 'Fri', value: 0.9 },
  { label: 'Sat', value: 0.1 },
  { label: 'Sun', value: 0.0 },
]

export function ConsumptionChart() {
  const total = chartData.reduce((sum, d) => sum + d.value, 0)

  const gridStroke = '#E4E4E7'
  const textFill = '#52525B'
  const axisStroke = '#E4E4E7'

  return (
    <div className="rounded-lg border border-[#E4E4E7] bg-white p-3 dark:border-[#262629] dark:bg-[#0A0A0A]">
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={chartData} margin={{ top: 8, right: 8, left: -24, bottom: -4 }}>
          <defs>
            <linearGradient id="yellowGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#FFF41F" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#FFF41F" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: textFill }}
            axisLine={{ stroke: axisStroke }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: textFill }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#ffffff',
              border: '1px solid #E4E4E7',
              borderRadius: '8px',
              fontSize: '12px',
              color: '#111111',
            }}
            itemStyle={{ color: '#7A6F00' }}
            labelStyle={{ fontWeight: 600, color: '#111111' }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#FFF41F"
            strokeWidth={2}
            fill="url(#yellowGradient)"
            dot={{ r: 3, fill: '#FFF41F', stroke: '#FFF41F', strokeWidth: 1 }}
            activeDot={{ r: 5, fill: '#FFF41F', stroke: '#111111', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
