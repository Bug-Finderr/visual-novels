"""Authlib OAuth client registry. Google is registered only when credentials
are present, so the app runs fine without them (login endpoints 503)."""
from authlib.integrations.starlette_client import OAuth

from app.config import config

oauth = OAuth()

if config.google_oauth_enabled:
    oauth.register(
        name="google",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
