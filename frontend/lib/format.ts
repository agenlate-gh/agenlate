/**
 * Formatting shared across screens, so the same number reads the same way
 * everywhere.
 */

/**
 * A dollar amount, at a precision that suits its size.
 *
 * Two decimals is wrong here. A room that has run once costs around $0.0002,
 * and rounding that to $0.00 tells a user their run was free when it was not.
 * Larger amounts get fewer decimals, because nobody reading a $12 bill cares
 * about the fourth one.
 */
export function formatUsd(amount: number): string {
  const decimals = amount >= 1 ? 2 : amount >= 0.01 ? 3 : 4
  return `$${amount.toFixed(decimals)}`
}

/**
 * How long ago, in the roughest terms that are still true.
 *
 * Relative rather than a timestamp: on a list of rooms the useful question is
 * which one was touched most recently, and "2 days ago" answers it without the
 * reader having to subtract dates.
 */
export function timeAgo(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'

  const steps: [number, string][] = [
    [60, 'minute'],
    [60, 'hour'],
    [24, 'day'],
    [7, 'week'],
  ]

  let value = seconds
  let unit = 'second'
  for (const [size, name] of steps) {
    if (value < size) break
    value = Math.floor(value / size)
    unit = name
  }

  if (unit === 'week' && value > 4) {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    })
  }
  return `${value} ${unit}${value === 1 ? '' : 's'} ago`
}
