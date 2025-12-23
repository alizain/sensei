"""Sensei - Intelligent documentation agent for AI coding assistants.

Usage:
    from sensei import mcp
    mcp.run()  # stdio transport
    # or
    app = mcp.http_app(path="/")  # HTTP transport (use path="/" when mounting)

For sub-modules:
    from sensei.kura import mcp as kura_mcp
    from sensei.scout import mcp as scout_mcp
    from sensei.tome import mcp as tome_mcp
"""
