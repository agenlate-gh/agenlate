/**
 * Configuration, read once and checked.
 *
 * Next.js inlines NEXT_PUBLIC_ variables at build time, so a missing one is not
 * an empty string at runtime — it is `undefined` baked into the bundle, and the
 * failure surfaces later as an unexplained network error against the URL
 * "undefined/api/agents". Checking here turns that into a message naming the
 * variable.
 */

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `Missing ${name}. Copy .env.example to .env.local and fill it in; ` +
        `these are read at build time, so restart the dev server afterwards.`,
    )
  }
  return value
}

export const env = {
  supabaseUrl: required(
    'NEXT_PUBLIC_SUPABASE_URL',
    process.env.NEXT_PUBLIC_SUPABASE_URL,
  ),
  supabaseAnonKey: required(
    'NEXT_PUBLIC_SUPABASE_ANON_KEY',
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  ),
  // Trailing slashes produce "//api/agents", which some proxies treat as a
  // different path than the one the backend registered.
  apiBaseUrl: (
    process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'
  ).replace(/\/+$/, ''),
} as const
