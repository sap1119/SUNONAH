"""Streaming utilities for LLM responses."""
from typing import Any, Dict, Union, Optional, AsyncGenerator, TypeVar
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

T = TypeVar('T')

@dataclass
class StreamingResponse:
    """Wrapper for streaming responses."""
    content: str
    is_final: bool = False
    latency_data: Optional[Dict[str, Any]] = None
    is_function: bool = False
    function_name: Optional[str] = None
    pre_call_message: Optional[str] = None

async def safe_async_iterator(obj: Any) -> AsyncGenerator[Any, None]:
    """Safely wrap an object in an async iterator."""
    if hasattr(obj, '__aiter__'):
        try:
            async for item in obj:
                yield item
        except Exception as e:
            logger.error(f"Error in async iteration: {e}")
            yield obj
    else:
        yield obj

def extract_content(data: Union[Dict[str, Any], Any], default: str = "") -> str:
    """Safely extract content from LLM response data."""
    try:
        if isinstance(data, dict):
            choices = data.get("choices", [])
            if choices and isinstance(choices[0], dict):
                # Try delta first for streaming
                content = choices[0].get("delta", {}).get("content")
                if content is None:
                    # Fall back to message for non-streaming
                    content = choices[0].get("message", {}).get("content")
                return content or default
        return str(data)
    except Exception as e:
        logger.error(f"Error extracting content: {e}")
        return default