"""SQLAlchemy database models for Sensei."""

from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import declarative_base, declared_attr


class TimestampMixin:
    """Mixin providing inserted_at and updated_at columns with PostgreSQL defaults."""

    @declared_attr
    def inserted_at(cls):
        return Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        )

    @declared_attr
    def updated_at(cls):
        return Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        )


Base = declarative_base()


class Query(TimestampMixin, Base):
    """Stores queries sent to Sensei and their responses."""

    __tablename__ = "queries"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    query = Column(Text, nullable=False)
    language = Column(String, nullable=True)  # Programming language filter
    library = Column(String, nullable=True)  # Library/framework name
    version = Column(String, nullable=True)  # Version specification
    output = Column(Text, nullable=False)  # Final text output from agent
    messages = Column(Text, nullable=True)  # JSON: all intermediate messages (tool calls, results)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("queries.id"), nullable=True)
    # Full-text search vector for efficient cache search
    query_tsvector = Column(
        TSVECTOR,
        Computed("to_tsvector('english', query)", persisted=True),
        nullable=True,
    )


class Rating(TimestampMixin, Base):
    """Stores user ratings for query responses (multi-dimensional)."""

    __tablename__ = "ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    query_id = Column(UUID(as_uuid=True), ForeignKey("queries.id"), nullable=False)

    correctness = Column(Integer, nullable=False)
    relevance = Column(Integer, nullable=False)
    usefulness = Column(Integer, nullable=False)
    reasoning = Column(Text, nullable=True)

    agent_model = Column(String, nullable=True)
    agent_system = Column(String, nullable=True)
    agent_version = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint("correctness BETWEEN 1 AND 5", name="correctness_range_check"),
        CheckConstraint("relevance BETWEEN 1 AND 5", name="relevance_range_check"),
        CheckConstraint("usefulness BETWEEN 1 AND 5", name="usefulness_range_check"),
    )


class Document(TimestampMixin, Base):
    """Container for documentation fetched from llms.txt sources.

    Documents are containers; sections hold the actual content.
    This separation allows FTS to work on sections that fit within PostgreSQL's
    tsvector size limit, while maintaining document-level metadata.

    Generation-based visibility:
    - generation_id: Groups documents from the same crawl
    - generation_active: Only active documents are visible to queries
    - Atomic swap: After crawl completes, flip active flag for new generation
    """

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    domain = Column(String, nullable=False, index=True)  # e.g. "react.dev"
    url = Column(String, nullable=False, unique=True)  # Full URL
    path = Column(String, nullable=False)  # e.g. "/docs/hooks/useState.md"
    content_hash = Column(String, nullable=False)  # For change detection on upsert
    content_refreshed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )  # When content was last refreshed
    # Generation-based crawl visibility
    generation_id = Column(UUID(as_uuid=True), nullable=False)  # Groups docs from same crawl
    generation_active = Column(Boolean, nullable=False, server_default="false")  # Only active docs visible to queries


class Section(TimestampMixin, Base):
    """Content section within a document, organized by markdown headings.

    Sections form a tree structure via parent_section_id, allowing:
    - FTS search on individual sections (always fits tsvector limit)
    - Subtree retrieval for specific headings
    - Full document reconstruction via position ordering
    - Heading breadcrumbs via parent traversal
    """

    __tablename__ = "sections"

    # default=uuid4 enables client-side ID generation for tree flattening
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid())
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_section_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=True,  # Null for root sections
        index=True,
    )
    heading = Column(String, nullable=True)  # Null for intro/root content before first heading
    level = Column(Integer, nullable=False)  # 0=root, 1=h1, 2=h2, etc.
    content = Column(Text, nullable=False)  # This section's markdown content
    position = Column(Integer, nullable=False)  # Global order in original document
    # Precomputed heading breadcrumb path (e.g., "API > Hooks > useState")
    # Populated at crawl time from ancestor traversal, avoids recursive CTE on search
    heading_path = Column(String, nullable=True)
    # Full-text search vector - computed by PostgreSQL on section content
    content_tsvector = Column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=True,
    )
