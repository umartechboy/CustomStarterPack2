import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://dhsblngaosaxxmwbiusa.supabase.co'
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRoc2Jsbmdhb3NheHhtd2JpdXNhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzAwNTgxNzEsImV4cCI6MjA4NTYzNDE3MX0.I_Ur14i2ykqmqk3TXPc0_4Yg3OpltazPZqdRA617UVc'

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://2j1q3wkmojqa3e-8000.proxy.runpod.net'
