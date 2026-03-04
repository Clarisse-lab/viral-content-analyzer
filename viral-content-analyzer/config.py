import os
from dotenv import load_dotenv

load_dotenv()

# AI
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Platforms
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_BUSINESS_ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_ORGANIZATION_ID = os.getenv("LINKEDIN_ORGANIZATION_ID", "")

# Apify (scraper alternativo para TikTok, Instagram, LinkedIn)
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")

# Search config
KEYWORDS = [k.strip() for k in os.getenv("KEYWORDS", "marketing digital,empreendedorismo").split(",")]
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "7"))

# Viral thresholds
YOUTUBE_MIN_VIEWS = int(os.getenv("YOUTUBE_MIN_VIEWS", "50000"))
INSTAGRAM_MIN_LIKES = int(os.getenv("INSTAGRAM_MIN_LIKES", "1000"))
TIKTOK_MIN_VIEWS = int(os.getenv("TIKTOK_MIN_VIEWS", "100000"))
LINKEDIN_MIN_REACTIONS = int(os.getenv("LINKEDIN_MIN_REACTIONS", "500"))

# Scheduler
DAILY_RUN_TIME = os.getenv("DAILY_RUN_TIME", "08:00")

# Analysis
ANALYSIS_LANGUAGE = os.getenv("ANALYSIS_LANGUAGE", "pt-BR")
