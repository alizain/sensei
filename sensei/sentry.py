"""Sentry initialization - import this module first to enable instrumentation."""

import os

import sentry_sdk

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    environment=os.environ.get("DOPPLER_ENVIRONMENT", "dev"),
)
