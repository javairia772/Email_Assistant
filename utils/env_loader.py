"""
Utility module for consistent environment variable loading across the project.
Ensures .envSecrets file is loaded first (for local development), then falls back
to .env or system environment variables (for Railway/production).
"""
from dotenv import load_dotenv
import os


def load_environment():
    """
    Load environment variables consistently across the project.
    
    Priority order:
    1. System environment variables (Railway, Docker, etc.) - highest priority
    2. .envSecrets file (local development secrets)
    3. .env file (local development defaults)
    
    This allows Railway/system env vars to override local .envSecrets file,
    which is the desired behavior for production deployments.
    """
    # Load .envSecrets first (local development secrets)
    # override=False means system env vars won't be overwritten by file
    load_dotenv('.envSecrets', override=False)
    
    # Also load .env if it exists (local development defaults)
    # override=False ensures system env vars still take precedence
    load_dotenv(override=False)


# Auto-load on import for convenience
load_environment()

