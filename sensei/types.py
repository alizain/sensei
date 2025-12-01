"""Type definitions for Sensei.

This module contains:
- Exception hierarchy for structured error handling
- Result types for tool return values
- Domain models shared across layers
- Value objects for normalization
"""

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar
from uuid import UUID

import tldextract
from pydantic import BaseModel, Field

# =============================================================================
# Exceptions
# =============================================================================


class SenseiError(Exception):
	"""Base for all Sensei errors."""

	pass


class BrokenInvariant(SenseiError):
	"""Setup/config error - cannot continue (e.g., missing API key)."""

	pass


class TransientError(SenseiError):
	"""Temporary failure - retry may succeed (e.g., network timeout)."""

	pass


class ToolError(SenseiError):
	"""Tool failed - try a different approach."""

	pass


# =============================================================================
# Result Types
# =============================================================================

T = TypeVar("T")


@dataclass
class Success(Generic[T]):
	"""Tool returned data successfully."""

	data: T


@dataclass
class NoResults:
	"""Tool executed successfully but found no results."""

	pass


# =============================================================================
# Value Objects
# =============================================================================


@dataclass(frozen=True)
class Domain:
	"""Normalized domain value object using public suffix resolution.

	Extracts the registrable domain (domain + public suffix) from any URL
	or domain string. Uses the Public Suffix List for accurate extraction.

	Examples:
	    Domain("https://www.example.com/path") -> Domain("example.com")
	    Domain("api.docs.example.com") -> Domain("example.com")
	    Domain("forums.bbc.co.uk") -> Domain("bbc.co.uk")
	    Domain("react.dev") -> Domain("react.dev")
	"""

	value: str

	def __post_init__(self) -> None:
		normalized = self._normalize(self.value)
		object.__setattr__(self, "value", normalized)

	@staticmethod
	def _normalize(raw: str) -> str:
		# tldextract handles URLs, domains, and edge cases
		extracted = tldextract.extract(raw)
		# top_domain_under_public_suffix gives us "domain.suffix" (e.g., "bbc.co.uk")
		registrable = extracted.top_domain_under_public_suffix
		if registrable:
			return registrable.lower()
		# Fallback for invalid/localhost domains
		return (extracted.domain or raw).lower()

	def __str__(self) -> str:
		return self.value

	@classmethod
	def from_url(cls, url: str) -> "Domain":
		"""Create Domain from a full URL."""
		return cls(url)


class SaveResult(Enum):
	"""Result of a save operation that may insert, update, or skip."""

	INSERTED = "inserted"
	UPDATED = "updated"
	SKIPPED = "skipped"  # Content unchanged


# =============================================================================
# Domain Models
# =============================================================================


class QueryResult(BaseModel):
	"""Result of a query operation."""

	query_id: UUID = Field(..., description="Unique identifier for this query")
	markdown: str = Field(..., description="Markdown documentation with code examples")


class Rating(BaseModel):
	"""Rating for a query response."""

	query_id: UUID = Field(..., description="The query ID to rate")
	correctness: int = Field(..., ge=1, le=5, description="Is the information/code correct? (1-5)")
	relevance: int = Field(..., ge=1, le=5, description="Did it answer the question? (1-5)")
	usefulness: int = Field(..., ge=1, le=5, description="Did it help solve the problem? (1-5)")
	reasoning: str | None = Field(None, description="Why these ratings? What changed from last time?")
	agent_model: str | None = Field(None, description="Model identifier")
	agent_system: str | None = Field(None, description="Agent system name")
	agent_version: str | None = Field(None, description="Agent system version")


class CacheHit(BaseModel):
	"""A cache search result summary."""

	query_id: UUID
	query_truncated: str = Field(..., description="First 100 chars of query")
	age_days: int
	library: str | None = None
	version: str | None = None


class SubSenseiResult(BaseModel):
	"""Result from spawning a sub-sensei."""

	query_id: UUID
	response_markdown: str
	from_cache: bool
	age_days: int | None = None


class DocumentContent(BaseModel):
	"""Content to save for a crawled document.

	Used by the tome crawler to pass document data to storage layer.
	Keeps the domain model as single source of truth.
	"""

	domain: str = Field(..., description="Source domain (e.g., 'react.dev')")
	url: str = Field(..., description="Full URL of the document")
	path: str = Field(..., description="Path portion of the URL")
	content: str = Field(..., description="Markdown content")
	content_hash: str = Field(..., description="Hash for change detection")
	depth: int = Field(..., ge=0, description="Crawl depth (0 = llms.txt, 1+ = linked)")


class IngestResult(BaseModel):
	"""Result of ingesting a domain's llms.txt documentation.

	Returned by the tome crawler after crawling a domain's llms.txt
	and its linked documents.
	"""

	domain: str = Field(..., description="The domain that was crawled")
	documents_added: int = Field(default=0, ge=0, description="Number of new documents added")
	documents_updated: int = Field(default=0, ge=0, description="Number of existing documents updated")
	documents_skipped: int = Field(default=0, ge=0, description="Number of unchanged documents skipped")
	errors: list[str] = Field(default_factory=list, description="Errors encountered during crawl")


class SearchResult(BaseModel):
	"""A full-text search result from section-based search.

	Returned by search_sections_fts() for tome_search functionality.
	"""

	url: str = Field(..., description="Full URL of the matching document")
	path: str = Field(..., description="Path portion of the URL")
	snippet: str = Field(..., description="Text snippet with search terms highlighted")
	rank: float = Field(..., description="Relevance score from ts_rank")
	heading_path: str = Field(default="", description="Breadcrumb path like 'API > Hooks > useState'")


@dataclass
class SectionData:
	"""Intermediate type for chunking algorithm output.

	Represents a section extracted from markdown content. Used by the chunker
	to return hierarchical sections that will be flattened for storage.
	"""

	heading: str | None  # Null for intro/root content before first heading
	level: int  # 0=root, 1=h1, 2=h2, etc.
	content: str  # This section's markdown content
	children: list["SectionData"]  # Child sections for building hierarchy


@dataclass
class TOCEntry:
	"""Table of contents entry for tome_toc().

	Represents a heading in the document hierarchy for navigation.
	"""

	heading: str
	level: int
	children: list["TOCEntry"]
