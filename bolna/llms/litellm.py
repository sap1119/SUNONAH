"""LiteLLM integration module for Bolna.AI."""
import os
import json
import time
import logging
from typing import (
    Any, Dict, Optional, Union, AsyncGenerator, Tuple, List, TypeVar
)
from dataclasses import dataclass, field

from litellm import acompletion
from dotenv import load_dotenv

from bolna.constants import DEFAULT_LANGUAGE_CODE
from bolna.helpers.utils import convert_to_request_log, compute_function_pre_call_message, now_ms
from .llm import BaseLLM
from .types import CompletionToolCall
from .streaming import safe_async_iterator
from bolna.helpers.logger_config import configure_logger

# Type definitions
T = TypeVar('T')
Message = Dict[str, str]
MetaInfo = Dict[str, Any]
LatencyData = Dict[str, Any]
StreamResponse = Tuple[Union[str, Dict[str, Any]], bool, LatencyData, bool, Optional[str], Optional[str]]

logger = configure_logger(__name__)
load_dotenv()

# Configure logging levels
for logger_name in ["LiteLLM", "LiteLLM Router", "LiteLLM Proxy"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

@dataclass
class StreamProcessor:
    """Helper class for processing stream chunks."""
    buffer: str = ""
    answer: str = ""
    received_textual_response: bool = False
    first_token_time: Optional[float] = None
    final_tool_calls_data: Dict[int, CompletionToolCall] = field(default_factory=dict)

    def process_tool_call(
        self,
        tool_call: Dict[str, Any],
        api_params: Dict[str, Any],
        language: str,
        gave_out_prefunction_call_message: bool,
        latency_data: Dict[str, Any]
    ) -> Optional[StreamResponse]:
        """Process a tool call and return response if needed."""
        if not isinstance(tool_call, dict):
            return None

        function_data = tool_call.get('function', {})
        if not isinstance(function_data, dict):
            return None

        called_fun = function_data.get('name')
        if not called_fun:
            return None

        self.final_tool_calls_data[tool_call.get('index', 0)] = {
            "index": tool_call.get('index', 0),
            "id": tool_call.get('id', str(time.time())),
            "function": {
                "name": called_fun,
                "arguments": function_data.get('arguments', '')
            },
            "type": "function"
        }

        if not gave_out_prefunction_call_message and not self.received_textual_response:
            api_tool_pre_call_message = api_params.get(called_fun, {}).get('pre_call_message')
            if api_tool_pre_call_message:
                pre_msg = compute_function_pre_call_message(language, called_fun, api_tool_pre_call_message)
                return (pre_msg, True, latency_data, False, called_fun, api_tool_pre_call_message)

        return None

    def process_content(
        self, 
        content: str,
        synthesize: bool,
        latency_data: Dict[str, Any]
    ) -> List[StreamResponse]:
        """Process content and return response chunks."""
        responses: List[StreamResponse] = []
        if content:
            self.received_textual_response = True
            self.answer += content
            self.buffer += content

            if synthesize and len(self.buffer) >= 40:  # Default buffer size
                split = self.buffer.rsplit(" ", 1)
                responses.append((split[0], False, latency_data, False, None, None))
                self.buffer = split[1] if len(split) > 1 else ""

        return responses

class LiteLLM(BaseLLM):
    """LiteLLM implementation for language model interaction."""

    def __init__(
        self,
        model: str,
        max_tokens: int = 30,
        buffer_size: int = 40,
        temperature: float = 0.0,
        language: str = DEFAULT_LANGUAGE_CODE,
        **kwargs: Any
    ) -> None:
        """Initialize LiteLLM instance."""
        super().__init__(max_tokens, buffer_size)
        self.model = model
        self.started_streaming = False
        self._active_streams: set[int] = set()
        self.language = language
        self.gave_out_prefunction_call_message = False

        # Setup model arguments
        self.model_args = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "model": self.model
        }

        # Configure API credentials
        self.api_key = kwargs.get("llm_key") or os.getenv('LITELLM_MODEL_API_KEY')
        self.api_base = kwargs.get("base_url") or os.getenv('LITELLM_MODEL_API_BASE')
        self.api_version = kwargs.get("api_version") or os.getenv('LITELLM_MODEL_API_VERSION')

        if self.api_key:
            self.model_args["api_key"] = self.api_key
        if self.api_base:
            self.model_args["api_base"] = self.api_base
        if self.api_version:
            self.model_args["api_version"] = self.api_version

        # Configure tools
        self.custom_tools = kwargs.get("api_tools")
        if self.custom_tools:
            self.trigger_function_call = True
            self.api_params = self.custom_tools['tools_params']
            self.tools = self.custom_tools['tools']
            logger.info(f"API Tools configured: {self.api_params}")
        else:
            self.trigger_function_call = False
            self.api_params = {}
            self.tools = None

        self.run_id = kwargs.get("run_id")

    async def generate_stream(
        self,
        messages: List[Message],
        synthesize: bool = True,
        meta_info: Optional[MetaInfo] = None
    ) -> AsyncGenerator[StreamResponse, None]:
        """Generate a stream of responses from the LLM."""
        if not messages:
            raise ValueError("No messages provided")

        processor = StreamProcessor()
        model_args = self.model_args.copy()
        model_args["messages"] = messages
        model_args["stream"] = True
        model_args["stop"] = ["User:"]

        if self.trigger_function_call and self.tools:
            model_args["tools"] = json.loads(self.tools) if isinstance(self.tools, str) else self.tools
            model_args["tool_choice"] = "auto"

        start_time = now_ms()
        latency_data = {
            "sequence_id": meta_info.get("sequence_id") if meta_info else None,
            "first_token_latency_ms": None,
            "total_stream_duration_ms": None,
        }

        stream_id = None
        try:
            response = await acompletion(**model_args)
            stream_id = id(response)
            self._active_streams.add(stream_id)

            async for chunk in safe_async_iterator(response):
                now = now_ms()
                if not processor.first_token_time:
                    processor.first_token_time = now
                    latency_data["first_token_latency_ms"] = now - start_time

                chunk_dict = chunk if isinstance(chunk, dict) else vars(chunk)
                choices = chunk_dict.get('choices', [])
                if not choices:
                    continue

                choice_data = choices[0]
                delta = choice_data.get('delta', {})
                if not isinstance(delta, dict):
                    continue

                # Process tool calls
                tool_calls = delta.get('tool_calls', [])
                for tool_call in tool_calls:
                    response = processor.process_tool_call(
                        tool_call,
                        self.api_params,
                        self.language,
                        self.gave_out_prefunction_call_message,
                        latency_data
                    )
                    if response:
                        self.gave_out_prefunction_call_message = True
                        yield response

                        if processor.buffer:
                            yield (processor.buffer, True, latency_data, False, None, None)
                            processor.buffer = ""

                # Process content
                content = str(delta.get('content', ''))
                for response in processor.process_content(content, synthesize, latency_data):
                    yield response

        except Exception as e:
            logger.error(f"Error in stream generation: {e}")
            if processor.buffer:
                yield (processor.buffer, True, latency_data, False, None, None)

        finally:
            if stream_id in self._active_streams:
                self._active_streams.remove(stream_id)

            latency_data["total_stream_duration_ms"] = now_ms() - start_time

            # Handle final tool calls if any
            if self.trigger_function_call and processor.final_tool_calls_data:
                first_tool = next(iter(processor.final_tool_calls_data.values()))
                func_name = first_tool["function"]["name"]
                args_str = first_tool["function"]["arguments"]

                try:
                    parsed_args = json.loads(args_str)
                except json.JSONDecodeError:
                    parsed_args = {"raw_args": args_str}

                func_conf = self.api_params.get(func_name, {})
                api_call_payload: Dict[str, Any] = {
                    "url": func_conf.get("url"),
                    "method": (func_conf.get("method") or "").lower(),
                    "param": func_conf.get("param"),
                    "api_token": func_conf.get("api_token"),
                    "headers": func_conf.get('headers'),
                    "model_args": model_args,
                    "meta_info": meta_info,
                    "called_fun": func_name,
                    "model_response": list(processor.final_tool_calls_data.values()),
                    "tool_call_id": first_tool["id"]
                }

                if isinstance(parsed_args, dict):
                    api_call_payload.update(parsed_args)  # type: ignore

                yield (api_call_payload, False, latency_data, True, None, None)

            # Final content yield
            if processor.buffer.strip():
                yield (processor.buffer, True, latency_data, False, None, None)

    async def generate(
        self,
        messages: List[Message],
        stream: bool = False,
        request_json: bool = False,
        meta_info: Optional[MetaInfo] = None
    ) -> str:
        """Generate a response from the LLM without streaming."""
        text = ""
        model_args = self.model_args.copy()
        model_args["messages"] = messages
        model_args["stream"] = False

        if request_json:
            model_args['response_format'] = {"type": "json_object"}

        logger.info(f'Request to litellm {model_args}')

        try:
            completion = await acompletion(**model_args)
            completion_data = completion if isinstance(completion, dict) else vars(completion)
            choices = completion_data.get('choices', [])
            if choices:
                first_choice = choices[0]
                message = first_choice.get('message', {}) if isinstance(first_choice, dict) else vars(first_choice).get('message', {})
                text = str(message.get('content', ''))
        except Exception as e:
            logger.error(f'Error generating response: {e}')

        return text or ""