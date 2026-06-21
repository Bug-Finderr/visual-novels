from google import genai

from app.config import config
from app.logger import logger

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "your_api_key_here":
            raise RuntimeError("GEMINI_API_KEY not set in .env — add your real API key")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
        logger.info("Gemini AI client initialized")
    return _client


models = config.models
