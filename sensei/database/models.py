"""SQLAlchemy database models for Sensei."""

from sqlalchemy import (
	CheckConstraint,
	Column,
	DateTime,
	ForeignKey,
	Integer,
	String,
	Text,
	func,
)
from sqlalchemy.dialects.postgresql import UUID
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
	# Cache hierarchy fields
	parent_id = Column(UUID(as_uuid=True), ForeignKey("queries.id"), nullable=True)
	depth = Column(Integer, server_default="0", nullable=False)


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
	"""Stores documentation fetched from llms.txt sources."""

	__tablename__ = "documents"

	id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
	domain = Column(String, nullable=False, index=True)  # e.g. "react.dev"
	url = Column(String, nullable=False, unique=True)  # Full URL
	path = Column(String, nullable=False)  # e.g. "/docs/hooks/useState.md"
	content = Column(Text, nullable=False)  # Markdown content
	content_hash = Column(String, nullable=False)  # For change detection on upsert
	content_refreshed_at = Column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)  # When content was last refreshed
	depth = Column(Integer, nullable=False, server_default="0")  # 0 = llms.txt, 1+ = linked
