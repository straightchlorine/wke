"""Read the text of an MCP tool result."""

from __future__ import annotations

import json
from typing import Any

from mcp.types import CallToolResult, ContentBlock, TextContent


def text_of_block(block: ContentBlock) -> str:
    """Return the text of a content block.

    Args:
        block: a content block of a tool result.

    Returns:
        str: the block's text.
    """
    assert isinstance(block, TextContent)
    return block.text


def text_of(result: CallToolResult) -> str:
    """Return the text of the first content block of a tool result.

    Args:
        result: a tool result.

    Returns:
        str: the first block's text.
    """
    return text_of_block(result.content[0])


def payload_of(result: CallToolResult) -> dict[str, Any]:
    """Parse the first content block of a tool result as a JSON object.

    Args:
        result: a tool result.

    Returns:
        dict[str, Any]: the decoded payload.
    """
    return json.loads(text_of(result))
