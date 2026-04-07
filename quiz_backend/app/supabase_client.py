from supabase import create_client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY


# Auth client (handles login/signup)
supabase_auth = create_client(SUPABASE_URL,SUPABASE_ANON_KEY )

# DB client (always safe)
supabase_db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)