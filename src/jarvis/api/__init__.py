"""HTTP surface for Jarvis, built on FastAPI.

Phase 1 exposes only a health check so the startup sequence has
something concrete to verify against. Feature endpoints (voice
control, plugin management, chat) are added in later phases as
FastAPI routers mounted from create_app().
"""
