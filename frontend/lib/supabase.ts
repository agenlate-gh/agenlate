/**
 * The Supabase browser client, used only for authentication.
 *
 * Everything else — agents, rooms, transcripts — goes through our own API
 * rather than talking to the database directly. That is deliberate: the
 * backend holds the orchestration, the spending limits and the key handling,
 * and a frontend that could reach the tables directly would be a second way
 * into the data with none of that in front of it.
 *
 * A plain browser client rather than the SSR helpers. Everything behind the
 * login is client-rendered — the room streams events and the API key lives in
 * the browser — so there is nothing for the server to render on a user's
 * behalf, and cookie-based session sharing would add moving parts for a
 * benefit we would never use.
 */

import { createClient } from '@supabase/supabase-js'

import { env } from './env'

export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    // Tokens last an hour. Without this a user who leaves a room open across
    // that boundary gets a 401 mid-run rather than a silent refresh.
    detectSessionInUrl: true,
  },
})

/** The caller's current access token, or null when signed out. */
export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}
