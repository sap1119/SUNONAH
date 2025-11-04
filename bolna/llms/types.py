"""Type definitions for LiteLLM integration."""
from typing import TypedDict, Optional, Any, Dict, Union, List
from dataclasses import dataclass
from typing_extensions import NotRequired

class CompletionFunction(TypedDict):
    """Function information in a completion."""
    name: str
    arguments: str

class CompletionToolCall(TypedDict):
    """Tool call in a completion response."""
    index: int
    id: str
    type: str
    function: CompletionFunction

class CompletionDelta(TypedDict):
    """Delta information in streaming responses."""
    content: Optional[str]
    tool_calls: Optional[List[CompletionToolCall]]
    function_call: Optional[Dict[str, Any]]

class MessageContent(TypedDict):
    """Message content in responses."""
    content: str
    role: str
    tool_calls: NotRequired[List[CompletionToolCall]]

class Choice(TypedDict):
    """A choice in a completion response."""
    message: MessageContent
    finish_reason: NotRequired[str]
    index: NotRequired[int]

class ModelResponse(TypedDict):
    """Complete model response."""
    id: str
    choices: List[Choice]
    model: str
    
@dataclass
class StreamingChoice:
    """Represents a streaming choice from the LLM."""
    delta: CompletionDelta
    index: int
    finish_reason: Optional[str] = None

@dataclass
class StreamChunk:
    """Represents a chunk from the streaming response."""
    id: str
    choices: List[StreamingChoice]
    model: str
    
@dataclass
class ToolCallOutput:
    """Represents the processed output from a tool call."""
    name: str
    arguments: str
    id: str
    index: int
    type: str = "function"

# Response type definitions
ResponseType = Union[ModelResponse, StreamChunk]
StreamingDeltaType = Union[CompletionDelta, Dict[str, Any]]
ToolCallType = Union[CompletionToolCall, Dict[str, Any]]