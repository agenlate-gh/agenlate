/**
 * The Agenlate mark and wordmark, from the brand kit.
 *
 * The mark is a figure — a ring for a head over an arch for shoulders — taken
 * from "Agenlate Visual_Mesa de trabajo 1.svg" and cropped to its own bounds.
 * It fills with `currentColor`, so it takes the colour of whatever it sits in
 * rather than carrying one of its own: yellow on the dark interface, near-black
 * on a yellow tile.
 *
 * The wordmark is set in Plus Jakarta Sans Bold, the typeface the brand sheet
 * names, with the slight tracking the kit uses.
 */

export function AgenlateMark({
  className,
  title = 'Agenlate',
}: {
  className?: string
  /** Null when the mark sits beside the name and would only repeat it. */
  title?: string | null
}) {
  return (
    <svg
      viewBox="356 354 250 231"
      fill="currentColor"
      className={className}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title ?? undefined}
    >
      <path d="M428.33,453.08c-0.63-3.25-0.97-6.6-0.97-10.03c0-29.25,23.84-52.96,53.24-52.96c29.4,0,53.24,23.71,53.24,52.96c0,3.34-0.32,6.6-0.92,9.76c11.49,4.5,22.25,10.45,32.05,17.62c2.83-8.62,4.36-17.82,4.36-27.38c0-48.75-39.73-88.27-88.74-88.27c-49.01,0-88.74,39.52-88.74,88.27c0,9.71,1.58,19.06,4.5,27.8C406.13,463.63,416.86,457.63,428.33,453.08z" />
      <path d="M391.87,584.43c0-0.05,0-0.1,0-0.15c0-48.75,39.73-88.27,88.74-88.27c49.01,0,88.74,39.52,88.74,88.27c0,0.05,0,0.1,0,0.15h35.49c0-0.05,0-0.1,0-0.15c0-68.25-55.62-123.57-124.23-123.57c-68.61,0-124.23,55.32-124.23,123.57c0,0.05,0,0.1,0,0.15H391.87z" />
    </svg>
  )
}

/** The mark on its yellow tile, as used for the app icon and small spaces. */
export function AgenlateTile({ className = 'size-8' }: { className?: string }) {
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-md bg-[#FFF41F] text-[#0A0A0A] ${className}`}
    >
      <AgenlateMark className="w-[62%]" title={null} />
    </span>
  )
}

/** Mark and name together. */
export function AgenlateLogo({ className }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className ?? ''}`}>
      <AgenlateTile />
      <span
        className="text-[18px] font-bold tracking-[0.01em] text-white"
        style={{ fontFamily: 'var(--font-jakarta), ui-sans-serif, sans-serif' }}
      >
        agenlate
      </span>
    </span>
  )
}
