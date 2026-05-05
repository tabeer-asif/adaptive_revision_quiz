import os
from dotenv import load_dotenv
from pydantic.v1 import BaseSettings

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")


class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    AI_ENABLED: bool = True

    class Config:
        env_file = ".env"

settings = Settings()