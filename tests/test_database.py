"""Tests for database operations."""

import hashlib
from uuid import UUID, uuid4

import pytest

from sensei.database import storage
from sensei.tome.crawler import flatten_section_tree
from sensei.types import Rating, SectionData


@pytest.mark.asyncio
async def test_save_query(test_db):
    """Test saving a query."""
    query = "How do I use FastAPI?"
    markdown = "# FastAPI Usage\n\nHere's how..."

    query_id = await storage.save_query(query=query, output=markdown)

    # Retrieve and verify
    retrieved = await storage.get_query(query_id)
    assert retrieved is not None
    assert retrieved.id == query_id
    assert retrieved.query == query
    assert retrieved.output == markdown


@pytest.mark.asyncio
async def test_save_query_with_messages(test_db):
    """Test saving a query with messages."""
    query = "What is Python?"
    markdown = "# Python\n\nPython is..."
    messages = b'[{"role": "user", "content": "test"}]'

    query_id = await storage.save_query(query=query, output=markdown, messages=messages)

    retrieved = await storage.get_query(query_id)
    assert retrieved is not None
    assert retrieved.messages == '[{"role": "user", "content": "test"}]'


@pytest.mark.asyncio
async def test_save_rating(test_db):
    """Test saving a rating."""
    # First create a query
    query_id = await storage.save_query(query="test query", output="test response")

    # Save a rating with all fields
    rating1 = Rating(
        query_id=query_id,
        correctness=5,
        relevance=4,
        usefulness=5,
        reasoning="Great response!",
        agent_model="model-x",
        agent_system="agent-y",
        agent_version="1.0",
    )
    await storage.save_rating(rating1)

    # Save another rating without optional fields
    rating2 = Rating(
        query_id=query_id,
        correctness=3,
        relevance=3,
        usefulness=2,
    )
    await storage.save_rating(rating2)


@pytest.mark.asyncio
async def test_get_query_not_found(test_db):
    """Test retrieving a non-existent query."""
    fake_uuid = UUID("00000000-0000-0000-0000-000000000000")
    retrieved = await storage.get_query(fake_uuid)
    assert retrieved is None


@pytest.mark.asyncio
async def test_save_query_with_parent_and_depth(test_db):
    """Test saving a sub-query with parent reference and depth."""
    # Create parent query
    parent_id = await storage.save_query(query="Main question?", output="Main answer")

    # Create child query
    child_id = await storage.save_query(
        query="Sub question?",
        output="Sub answer",
        parent_id=parent_id,
        depth=1,
    )

    # Verify child has correct parent and depth
    child = await storage.get_query(child_id)
    assert child is not None
    assert child.parent_id == parent_id
    assert child.depth == 1

    # Verify parent has no parent and depth 0
    parent = await storage.get_query(parent_id)
    assert parent is not None
    assert parent.parent_id is None
    assert parent.depth == 0


@pytest.mark.asyncio
async def test_search_queries(test_db):
    """Test search queries using ILIKE."""
    # Insert test data
    await storage.save_query(query="How do React hooks work?", output="Answer 1", library="react", version="18")
    await storage.save_query(query="React component lifecycle", output="Answer 2", library="react")
    await storage.save_query(query="Python async await", output="Answer 3", library="python")

    # Search for "React"
    results = await storage.search_queries(["React"], limit=10)
    assert len(results) == 2

    # Search that matches nothing
    results = await storage.search_queries(["nonexistent"], limit=10)
    assert len(results) == 0


# =============================================================================
# Document and Section Storage Tests
# =============================================================================


def _hash(content: str) -> str:
    """Helper to compute content hash."""
    return hashlib.sha256(content.encode()).hexdigest()


@pytest.mark.asyncio
async def test_insert_document(test_db):
    """Test inserting a new document with generation."""
    generation_id = uuid4()
    doc_id = await storage.insert_document(
        domain="react.dev",
        url="https://react.dev/docs/hooks/useState",
        path="/docs/hooks/useState",
        content_hash=_hash("content"),
        generation_id=generation_id,
    )

    assert doc_id is not None

    # Document is not yet active - get_document_by_url with active_only=True should return None
    doc = await storage.get_document_by_url("https://react.dev/docs/hooks/useState", active_only=True)
    assert doc is None

    # But with active_only=False it should exist
    doc = await storage.get_document_by_url("https://react.dev/docs/hooks/useState", active_only=False)
    assert doc is not None
    assert doc.domain == "react.dev"
    assert doc.path == "/docs/hooks/useState"
    assert doc.generation_id == generation_id
    assert doc.generation_active is False


@pytest.mark.asyncio
async def test_activate_generation(test_db):
    """Test activating a generation makes documents visible."""
    generation_id = uuid4()

    # Insert document (inactive)
    doc_id = await storage.insert_document(
        domain="example.com",
        url="https://example.com/doc",
        path="/doc",
        content_hash=_hash("content"),
        generation_id=generation_id,
    )

    # Not visible yet
    assert await storage.get_document_by_url("https://example.com/doc", active_only=True) is None

    # Activate generation
    count = await storage.activate_generation("example.com", generation_id)
    assert count == 1

    # Now visible
    doc = await storage.get_document_by_url("https://example.com/doc", active_only=True)
    assert doc is not None
    assert doc.generation_active is True


@pytest.mark.asyncio
async def test_activate_generation_deactivates_old(test_db):
    """Test that activating a new generation deactivates old ones."""
    gen1 = uuid4()
    gen2 = uuid4()

    # Insert and activate first generation
    await storage.insert_document(
        domain="example.com",
        url="https://example.com/doc1",
        path="/doc1",
        content_hash=_hash("v1"),
        generation_id=gen1,
    )
    await storage.activate_generation("example.com", gen1)

    # First doc is active
    assert await storage.get_document_by_url("https://example.com/doc1", active_only=True) is not None

    # Insert second generation with different URL
    await storage.insert_document(
        domain="example.com",
        url="https://example.com/doc2",
        path="/doc2",
        content_hash=_hash("v2"),
        generation_id=gen2,
    )
    await storage.activate_generation("example.com", gen2)

    # Now first doc is inactive, second is active
    assert await storage.get_document_by_url("https://example.com/doc1", active_only=True) is None
    assert await storage.get_document_by_url("https://example.com/doc2", active_only=True) is not None


@pytest.mark.asyncio
async def test_cleanup_old_generations(test_db):
    """Test cleanup removes inactive documents."""
    gen1 = uuid4()
    gen2 = uuid4()

    # Insert and activate first generation
    await storage.insert_document(
        domain="example.com",
        url="https://example.com/old",
        path="/old",
        content_hash=_hash("old"),
        generation_id=gen1,
    )
    await storage.activate_generation("example.com", gen1)

    # Insert and activate second generation
    await storage.insert_document(
        domain="example.com",
        url="https://example.com/new",
        path="/new",
        content_hash=_hash("new"),
        generation_id=gen2,
    )
    await storage.activate_generation("example.com", gen2)

    # Old doc still exists (just inactive)
    assert await storage.get_document_by_url("https://example.com/old", active_only=False) is not None

    # Cleanup
    deleted = await storage.cleanup_old_generations("example.com")
    assert deleted == 1

    # Old doc is gone
    assert await storage.get_document_by_url("https://example.com/old", active_only=False) is None

    # New doc still exists
    assert await storage.get_document_by_url("https://example.com/new", active_only=True) is not None


@pytest.mark.asyncio
async def test_get_document_by_url_not_found(test_db):
    """Test retrieving a non-existent document."""
    doc = await storage.get_document_by_url("https://nonexistent.com/doc")
    assert doc is None


@pytest.mark.asyncio
async def test_save_and_get_sections(test_db):
    """Test saving sections for a document and retrieving them."""
    # Create and activate document
    generation_id = uuid4()
    doc_id = await storage.insert_document(
        domain="react.dev",
        url="https://react.dev/hooks",
        path="/hooks",
        content_hash=_hash("hooks"),
        generation_id=generation_id,
    )
    await storage.activate_generation("react.dev", generation_id)

    # Create sections with hierarchy
    section_tree = SectionData(
        heading=None,
        level=0,
        content="# React Hooks Overview",
        children=[
            SectionData(
                heading="useState",
                level=2,
                content="## useState\n\nuseState lets you manage state",
                children=[],
            ),
            SectionData(
                heading="useEffect",
                level=2,
                content="## useEffect\n\nuseEffect lets you synchronize",
                children=[],
            ),
        ],
    )

    # Flatten tree and save sections
    sections = flatten_section_tree(section_tree, doc_id)
    count = await storage.save_sections(doc_id, sections)
    assert count == 3  # Root + 2 children

    # Retrieve sections (only works for active documents)
    retrieved = await storage.get_sections_by_document("react.dev", "/hooks")
    assert len(retrieved) == 3

    # Verify order (by position)
    assert retrieved[0].level == 0
    assert retrieved[1].heading == "useState"
    assert retrieved[2].heading == "useEffect"


@pytest.mark.asyncio
async def test_search_sections_fts(test_db):
    """Test full-text search on sections with heading_path."""
    # Create and activate document with sections
    generation_id = uuid4()
    doc_id = await storage.insert_document(
        domain="react.dev",
        url="https://react.dev/hooks",
        path="/hooks",
        content_hash=_hash("hooks"),
        generation_id=generation_id,
    )
    await storage.activate_generation("react.dev", generation_id)

    section_tree = SectionData(
        heading=None,
        level=0,
        content="",
        children=[
            SectionData(
                heading="useState Hook",
                level=2,
                content="## useState Hook\n\nuseState is a React Hook that lets you add state variable to component.",
                children=[],
            ),
            SectionData(
                heading="useEffect Hook",
                level=2,
                content="## useEffect Hook\n\nuseEffect is a React Hook that lets you synchronize with external systems.",
                children=[],
            ),
        ],
    )
    sections = flatten_section_tree(section_tree, doc_id)
    await storage.save_sections(doc_id, sections)

    # Search for "Hook"
    results = await storage.search_sections_fts("react.dev", "Hook")
    assert len(results) >= 1
    # Results should have heading_path
    assert all(hasattr(r, "heading_path") for r in results)

    # Search with no matches
    results = await storage.search_sections_fts("react.dev", "nonexistent")
    assert len(results) == 0

    # Empty query returns empty
    results = await storage.search_sections_fts("react.dev", "")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_sections_fts_inactive_not_found(test_db):
    """Test that FTS doesn't find inactive documents."""
    generation_id = uuid4()
    doc_id = await storage.insert_document(
        domain="test.dev",
        url="https://test.dev/doc",
        path="/doc",
        content_hash=_hash("doc"),
        generation_id=generation_id,
    )
    # NOT activating the generation

    section_tree = SectionData(
        heading="Test",
        level=1,
        content="# Test\n\nThis is searchable content.",
        children=[],
    )
    sections = flatten_section_tree(section_tree, doc_id)
    await storage.save_sections(doc_id, sections)

    # Search should find nothing (document not active)
    results = await storage.search_sections_fts("test.dev", "searchable")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_delete_documents_by_domain(test_db):
    """Test deleting all documents for a domain."""
    gen1 = uuid4()
    gen2 = uuid4()

    # Insert documents for multiple domains
    await storage.insert_document(
        domain="react.dev",
        url="https://react.dev/doc1",
        path="/doc1",
        content_hash=_hash("r1"),
        generation_id=gen1,
    )
    await storage.insert_document(
        domain="react.dev",
        url="https://react.dev/doc2",
        path="/doc2",
        content_hash=_hash("r2"),
        generation_id=gen1,
    )
    await storage.insert_document(
        domain="vue.js.org",
        url="https://vue.js.org/doc1",
        path="/doc1",
        content_hash=_hash("v1"),
        generation_id=gen2,
    )

    # Delete react.dev documents
    count = await storage.delete_documents_by_domain("react.dev")
    assert count == 2

    # Verify react.dev docs are gone
    doc1 = await storage.get_document_by_url("https://react.dev/doc1", active_only=False)
    doc2 = await storage.get_document_by_url("https://react.dev/doc2", active_only=False)
    assert doc1 is None
    assert doc2 is None

    # Verify vue.js.org doc still exists
    vue_doc = await storage.get_document_by_url("https://vue.js.org/doc1", active_only=False)
    assert vue_doc is not None


@pytest.mark.asyncio
async def test_delete_documents_by_domain_none_exist(test_db):
    """Test deleting documents for a domain with no documents."""
    count = await storage.delete_documents_by_domain("nonexistent.com")
    assert count == 0


# =============================================================================
# Migration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_migration_schema_matches_models(test_db):
    """Verify that migrations create the schema matching our models."""
    from sqlalchemy import inspect

    async with test_db.connect() as conn:
        # Get inspector in sync context
        def get_tables(connection):
            inspector = inspect(connection)
            return inspector.get_table_names()

        tables = await conn.run_sync(get_tables)

    # Check all expected tables exist
    expected_tables = {"queries", "ratings", "documents", "sections", "alembic_version"}
    assert set(tables) == expected_tables


@pytest.mark.asyncio
async def test_migration_queries_columns(test_db):
    """Verify queries table has all expected columns."""
    from sqlalchemy import inspect

    async with test_db.connect() as conn:

        def get_columns(connection):
            inspector = inspect(connection)
            return {col["name"] for col in inspector.get_columns("queries")}

        columns = await conn.run_sync(get_columns)

    expected_columns = {
        "id",
        "query",
        "language",
        "library",
        "version",
        "output",
        "messages",
        "parent_id",
        "depth",
        "inserted_at",
        "updated_at",
    }
    assert columns == expected_columns


@pytest.mark.asyncio
async def test_migration_ratings_columns(test_db):
    """Verify ratings table has all expected columns."""
    from sqlalchemy import inspect

    async with test_db.connect() as conn:

        def get_columns(connection):
            inspector = inspect(connection)
            return {col["name"] for col in inspector.get_columns("ratings")}

        columns = await conn.run_sync(get_columns)

    expected_columns = {
        "id",
        "query_id",
        "correctness",
        "relevance",
        "usefulness",
        "reasoning",
        "agent_model",
        "agent_system",
        "agent_version",
        "inserted_at",
        "updated_at",
    }
    assert columns == expected_columns


@pytest.mark.asyncio
async def test_migration_documents_columns(test_db):
    """Verify documents table has expected columns with generation support."""
    from sqlalchemy import inspect

    async with test_db.connect() as conn:

        def get_columns(connection):
            inspector = inspect(connection)
            return {col["name"] for col in inspector.get_columns("documents")}

        columns = await conn.run_sync(get_columns)

    # Document is a container with generation-based visibility
    expected_columns = {
        "id",
        "domain",
        "url",
        "path",
        "content_hash",
        "content_refreshed_at",
        "generation_id",
        "generation_active",
        "inserted_at",
        "updated_at",
    }
    assert columns == expected_columns


@pytest.mark.asyncio
async def test_migration_sections_columns(test_db):
    """Verify sections table has all expected columns."""
    from sqlalchemy import inspect

    async with test_db.connect() as conn:

        def get_columns(connection):
            inspector = inspect(connection)
            return {col["name"] for col in inspector.get_columns("sections")}

        columns = await conn.run_sync(get_columns)

    expected_columns = {
        "id",
        "document_id",
        "parent_section_id",
        "heading",
        "level",
        "content",
        "position",
        "search_vector",
        "inserted_at",
        "updated_at",
    }
    assert columns == expected_columns


@pytest.mark.asyncio
async def test_migration_sections_fts_index(test_db):
    """Verify sections table has FTS index."""
    from sqlalchemy import inspect

    async with test_db.connect() as conn:

        def get_indexes(connection):
            inspector = inspect(connection)
            return {idx["name"] for idx in inspector.get_indexes("sections")}

        indexes = await conn.run_sync(get_indexes)

    assert "idx_sections_search_vector" in indexes


@pytest.mark.asyncio
async def test_migration_documents_domain_index(test_db):
    """Verify documents table has domain index and active partial index."""
    from sqlalchemy import inspect

    async with test_db.connect() as conn:

        def get_indexes(connection):
            inspector = inspect(connection)
            return {idx["name"] for idx in inspector.get_indexes("documents")}

        indexes = await conn.run_sync(get_indexes)

    assert "ix_documents_domain" in indexes
    assert "idx_documents_domain_active" in indexes  # Partial index for active docs


@pytest.mark.asyncio
async def test_migration_ratings_check_constraints(test_db):
    """Verify ratings constraints are enforced at both Pydantic and DB levels."""
    from pydantic import ValidationError

    query_id = await storage.save_query(query="test", output="test")

    # Pydantic validation catches invalid values before DB
    with pytest.raises(ValidationError):
        Rating(
            query_id=query_id,
            correctness=6,  # Invalid: must be <= 5
            relevance=3,
            usefulness=3,
        )

    with pytest.raises(ValidationError):
        Rating(
            query_id=query_id,
            correctness=0,  # Invalid: must be >= 1
            relevance=3,
            usefulness=3,
        )

    # Valid rating should work
    valid_rating = Rating(
        query_id=query_id,
        correctness=5,
        relevance=5,
        usefulness=5,
    )
    await storage.save_rating(valid_rating)  # Should not raise


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


@pytest.mark.asyncio
async def test_save_query_with_all_optional_fields(test_db):
    """Test saving a query with all optional fields populated."""
    query_id = await storage.save_query(
        query="How to use TypeScript generics?",
        output="# Generics\n\nGeneric types allow...",
        messages=b'[{"role": "assistant", "content": "Let me explain..."}]',
        language="typescript",
        library="typescript",
        version="5.0",
    )

    retrieved = await storage.get_query(query_id)
    assert retrieved is not None
    assert retrieved.language == "typescript"
    assert retrieved.library == "typescript"
    assert retrieved.version == "5.0"


@pytest.mark.asyncio
async def test_save_query_unicode_content(test_db):
    """Test saving queries with unicode characters."""
    query = "Comment utiliser les hooks React? 你好 🚀"
    output = "# React Hooks\n\nLes hooks permettent... émojis: 🎉 汉字"

    query_id = await storage.save_query(query=query, output=output)

    retrieved = await storage.get_query(query_id)
    assert retrieved is not None
    assert retrieved.query == query
    assert retrieved.output == output


@pytest.mark.asyncio
async def test_search_queries_case_insensitive(test_db):
    """Test that search is case insensitive."""
    await storage.save_query(query="How do REACT hooks work?", output="Answer")

    # Should find regardless of case
    results = await storage.search_queries(["react"])
    assert len(results) == 1

    results = await storage.search_queries(["REACT"])
    assert len(results) == 1

    results = await storage.search_queries(["ReAcT"])
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_queries_partial_match(test_db):
    """Test that search matches partial terms."""
    await storage.save_query(query="Understanding useState in React", output="Answer")

    # Should match partial term
    results = await storage.search_queries(["State"])
    assert len(results) == 1

    results = await storage.search_queries(["stand"])
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_queries_respects_limit(test_db):
    """Test that search limit is respected."""
    # Insert many queries
    for i in range(10):
        await storage.save_query(query=f"React question {i}", output=f"Answer {i}")

    # Verify limit works
    results = await storage.search_queries(["React"], limit=3)
    assert len(results) == 3

    results = await storage.search_queries(["React"], limit=5)
    assert len(results) == 5


@pytest.mark.asyncio
async def test_document_url_uniqueness(test_db):
    """Test that document URLs are unique within a generation."""
    import sqlalchemy.exc

    url = "https://unique.com/doc"
    generation_id = uuid4()

    # Insert first document
    doc_id1 = await storage.insert_document(
        domain="unique.com",
        url=url,
        path="/doc",
        content_hash=_hash("Version 1"),
        generation_id=generation_id,
    )
    assert doc_id1 is not None

    # Inserting same URL again should fail (unique constraint)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await storage.insert_document(
            domain="unique.com",
            url=url,
            path="/doc",
            content_hash=_hash("Version 2"),
            generation_id=generation_id,
        )


@pytest.mark.asyncio
async def test_query_parent_child_chain(test_db):
    """Test multi-level parent-child query chain."""
    # Create chain: root -> child1 -> grandchild
    root_id = await storage.save_query(query="Root query", output="Root answer", depth=0)

    child_id = await storage.save_query(
        query="Child query",
        output="Child answer",
        parent_id=root_id,
        depth=1,
    )

    grandchild_id = await storage.save_query(
        query="Grandchild query",
        output="Grandchild answer",
        parent_id=child_id,
        depth=2,
    )

    # Verify chain
    root = await storage.get_query(root_id)
    child = await storage.get_query(child_id)
    grandchild = await storage.get_query(grandchild_id)

    assert root.parent_id is None
    assert root.depth == 0

    assert child.parent_id == root_id
    assert child.depth == 1

    assert grandchild.parent_id == child_id
    assert grandchild.depth == 2


@pytest.mark.asyncio
async def test_save_rating_foreign_key_constraint(test_db):
    """Test that rating requires valid query_id."""
    import sqlalchemy.exc

    fake_query_id = UUID("11111111-1111-1111-1111-111111111111")

    # Should fail due to foreign key constraint
    rating = Rating(
        query_id=fake_query_id,
        correctness=3,
        relevance=3,
        usefulness=3,
    )

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await storage.save_rating(rating)
