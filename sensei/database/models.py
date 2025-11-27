"""SQLAlchemy database models for Sensei."""

from datetime import UTC, datetime

from sqlalchemy import (
	CheckConstraint,
	Column,
	DateTime,
	ForeignKey,
	Integer,
	String,
	Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Query(Base):
	"""Stores queries sent to Sensei and their responses."""

	__tablename__ = "queries"

	query_id = Column(String, primary_key=True)
	query = Column(Text, nullable=False)
	language = Column(String, nullable=True)  # Programming language filter
	library = Column(String, nullable=True)  # Library/framework name
	version = Column(String, nullable=True)  # Version specification
	output = Column(Text, nullable=False)  # Final text output from agent
	messages = Column(Text, nullable=True)  # JSON: all intermediate messages (tool calls, results)
	sources_used = Column(Text, nullable=True)  # JSON string array of source names
	created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
	# Cache hierarchy fields
	parent_query_id = Column(String, ForeignKey("queries.query_id"), nullable=True)
	depth = Column(Integer, default=0, nullable=False)


class Rating(Base):
	"""Stores user ratings for query responses (multi-dimensional)."""

	__tablename__ = "ratings"

	id = Column(Integer, primary_key=True, autoincrement=True)
	query_id = Column(String, ForeignKey("queries.query_id"), nullable=False)

	correctness = Column(Integer, nullable=False)
	relevance = Column(Integer, nullable=False)
	usefulness = Column(Integer, nullable=False)
	reasoning = Column(Text, nullable=True)

	agent_model = Column(String, nullable=True)
	agent_system = Column(String, nullable=True)
	agent_version = Column(String, nullable=True)

	created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

	__table_args__ = (
		CheckConstraint("correctness BETWEEN 1 AND 5", name="correctness_range_check"),
		CheckConstraint("relevance BETWEEN 1 AND 5", name="relevance_range_check"),
		CheckConstraint("usefulness BETWEEN 1 AND 5", name="usefulness_range_check"),
	)
