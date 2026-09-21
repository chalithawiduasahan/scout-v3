import { createClient } from '@supabase/supabase-js';

// These are the same VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY env vars
// that were already sitting (unused) in Vercel's Environment Variables.
// The anon key is safe to expose in the browser by design — real
// protection comes from Supabase Auth + Row Level Security, not from
// hiding this key.
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

if (!supabaseUrl || !supabaseAnonKey) {
  // Fails loudly in the console rather than silently breaking auth,
  // since a missing env var here means nobody can sign in at all.
  console.error(
    'Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY. Auth will not work until these are set in Vercel.'
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);