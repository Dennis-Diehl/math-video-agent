"""Application configuration via pydantic-settings.

Loads settings from environment variables / a `.env` file. Code that
needs the Gemini API key or model names imports the shared `settings`
instance from here instead of reading `os.environ` directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object for the whole pipeline."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Gemini API
    gemini_api_key: str = ""
    gemini_model_flash: str = "gemini-3.5-flash"
    gemini_model_flash_lite: str = "gemini-3.5-flash-lite"

    # TTS
    kokoro_voice: str = "af_heart"
    kokoro_lang_code: str = "a"  # american english

    # API / job orchestration
    job_output_dir: str = "media/jobs"


settings = Settings()
