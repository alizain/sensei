"""Tome: Documentation repository from llms.txt sources."""

from sensei.tome.crawler import ingest_domain
from sensei.tome.service import tome_get, tome_search

__all__ = ["ingest_domain", "tome_get", "tome_search"]
