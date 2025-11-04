import asyncio
import traceback
import time
from typing import Optional, Dict, Any, AsyncGenerator
import logging
from contextlib import AsyncExitStack

from bolna.models import Task, LlmAgent, Transcriber, Synthesizer
from bolna.helpers.logger_config import configure_logger
from bolna.helpers.analytics_helpers import track_request
from bolna.llms.litellm import LiteLLM as get_llm_agent
from bolna.input_handlers.default import DefaultInputHandler as get_input_handler
from bolna.output_handlers.default import DefaultOutputHandler as get_output_handler

logger = configure_logger(__name__)

class TaskError(Exception):
    """Base exception for task-related errors"""
    pass

class InputProcessingError(TaskError):
    """Raised when input processing fails"""
    pass

class LLMError(TaskError):
    """Raised when LLM generation fails"""
    pass

class OutputProcessingError(TaskError):
    """Raised when output processing fails"""
    pass

class TaskManager:
    def __init__(self, task: Task, session_id: str, sequence_id: Optional[str] = None):
        """Initialize TaskManager with task configuration and session information.
        
        Args:
            task: Task configuration object
            session_id: Unique session identifier
            sequence_id: Optional sequence identifier, defaults to session_id
            
        The TaskManager handles initialization of:
        - Input/Output queues for async communication
        - Resource cleanup through AsyncExitStack
        - LLM agent configuration
        - Input/Output handlers setup
        """
        self.task = task
        self.session_id = session_id
        self.sequence_id = sequence_id or session_id
        self.turn_id = 0
        
        # Initialize queues with maxsize to prevent memory issues
        self.input_queue = asyncio.Queue(maxsize=100)
        self.output_queue = asyncio.Queue(maxsize=100)
        
        # Resource management
        self.exit_stack = AsyncExitStack()
        self.is_initialized = False
        self._closed = False  # Track if manager has been closed
        
        # Initialize LLM agent
        llm_config = task.tools_config.llm_agent.llm_config
        self.llm_agent = get_llm_agent(
            model=llm_config.model,
            temperature=llm_config.temperature,
            max_tokens=llm_config.max_tokens or 100,
            system_prompt=llm_config.system_prompt,
            functions=llm_config.functions,
            provider_config=llm_config.provider_config
        )
        
        # Initialize input handler with proper configuration
        if task.tools_config.transcriber:
            self.input_handler = get_input_handler()
            if self.input_handler:
                self.input_handler.queues = {
                    'transcriber': self.input_queue,
                    'llm': self.output_queue
                }
        else:
            self.input_handler = None
            
        # Initialize output handler with proper configuration
        if task.tools_config.synthesizer:
            self.output_handler = get_output_handler()
            self.output_handler.websocket = None  # Will be set when needed
            self.output_handler.mark_event_meta_data = {}  # Initialize empty metadata
        else:
            self.output_handler = None

    async def _handle_input(self, user_input: str) -> str:
        """Handle user input through transcription if needed"""
        if not self.input_handler:
            return user_input
            
        # Create the message packet
        message = {
            "type": "text",
            "data": user_input
        }
        await self.input_handler.process_message(message)
        return user_input

    async def _handle_output(self, agent_response: str) -> AsyncGenerator[Any, None]:
        """Handle agent output through synthesis if needed"""
        if not self.output_handler:
            yield agent_response
            return
            
        # Create the packet
        packet = {
            "data": agent_response,
            "meta_info": {
                "type": "text"
            }
        }
        await self.output_handler.handle(packet)
        yield agent_response

    async def initialize(self):
        """Initialize resources and connections"""
        if not self.is_initialized:
            try:
                if self.input_handler:
                    await self.exit_stack.enter_async_context(self.input_handler)
                if self.output_handler:
                    await self.exit_stack.enter_async_context(self.output_handler)
                self.is_initialized = True
            except Exception as e:
                await self.cleanup()
                raise TaskError(f"Failed to initialize task: {str(e)}")

    async def cleanup(self):
        """Clean up resources and connections.
        
        Ensures proper cleanup of:
        - Input/Output handlers through AsyncExitStack
        - Any pending queue items
        - LLM agent resources
        """
        if self._closed:
            return
            
        try:
            # Clear any pending queue items
            while not self.input_queue.empty():
                try:
                    self.input_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                    
            while not self.output_queue.empty():
                try:
                    self.output_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                    
            # Cleanup handlers
            await self.exit_stack.aclose()
            
            # LLM agent cleanup (if any) would happen here
            # Currently no explicit cleanup needed for LiteLLM
                    
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
        finally:
            self.is_initialized = False
            self._closed = True

    async def process(self, user_input: str) -> AsyncGenerator[Any, None]:
        """Process a single turn in the task with retries and rate limiting"""
        if not self.is_initialized:
            await self.initialize()

        self.turn_id += 1
        meta_info = {
            "session_id": self.session_id,
            "sequence_id": self.sequence_id,
            "turn_id": self.turn_id,
            "timestamp": time.time()
        }
        
        max_retries = 3
        retry_delay = 1  # Initial delay in seconds
        
        for attempt in range(max_retries):
            try:
                # Handle input with timeout
                try:
                    async with asyncio.timeout(10):  # 10 second timeout
                        processed_input = await self._handle_input(user_input)
                        if not processed_input:
                            raise InputProcessingError("Failed to process input")
                        track_request(processed_input, meta_info, source="user", direction="request")
                except asyncio.TimeoutError:
                    raise InputProcessingError("Input processing timed out")
                except Exception as e:
                    logger.error(f"Input processing error: {str(e)}")
                    raise InputProcessingError(f"Input processing failed: {str(e)}")
                
                # Rate limiting
                await asyncio.sleep(0.1)  # Basic rate limiting
                
                # Get agent response through LLM with timeout
                try:
                    async with asyncio.timeout(30):  # 30 second timeout for LLM
                        messages = [{"role": "user", "content": processed_input}]
                        agent_response = await self.llm_agent.generate(messages)
                        if not agent_response:
                            raise LLMError("No response generated from LLM")
                        track_request(agent_response, meta_info, source="assistant", direction="response")
                except asyncio.TimeoutError:
                    raise LLMError("LLM generation timed out")
                except Exception as e:
                    logger.error(f"LLM error: {str(e)}")
                    raise LLMError(f"LLM generation failed: {str(e)}")
                
                # Handle output with timeout
                try:
                    async with asyncio.timeout(10):  # 10 second timeout
                        async for chunk in self._handle_output(agent_response):
                            if chunk:
                                yield chunk
                except asyncio.TimeoutError:
                    raise OutputProcessingError("Output processing timed out")
                except Exception as e:
                    logger.error(f"Output processing error: {str(e)}")
                    raise OutputProcessingError(f"Output processing failed: {str(e)}")
                
                # If we get here, processing was successful
                break
                
            except TaskError as e:
                error_msg = str(e)
                logger.error(f"Task error (attempt {attempt + 1}/{max_retries}): {error_msg}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                    
                yield f"I encountered a task error after {max_retries} attempts: {error_msg}. Please try again."
                
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                yield f"An unexpected error occurred: {str(e)}. Please try again."
                break
                
            finally:
                # Clear queues
                while not self.input_queue.empty():
                    try:
                        self.input_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                        
                while not self.output_queue.empty():
                    try:
                        self.output_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                        
    async def run(self) -> Dict[str, Any]:
        """Run the task and return the output.
        
        Returns:
            Dictionary containing task output and metadata
        """
        try:
            # Initialize if not already done
            if not self.is_initialized:
                await self.initialize()
                
            # Process the task's default input
            result = {}
            async for output in self.process("Hello"):
                # Collect output chunks
                if isinstance(output, dict):
                    result.update(output)
                else:
                    result["response"] = output
                    
            # Add metadata
            result.update({
                "session_id": self.session_id,
                "sequence_id": self.sequence_id,
                "turn_id": self.turn_id,
                "timestamp": time.time()
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Task run failed: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise
            
    async def load_prompt(self, agent_name: str, task_id: int, local: bool = False, **kwargs):
        """Load and initialize the prompt for this task.
        
        Args:
            agent_name: Name of the agent this task belongs to
            task_id: ID of this task
            local: Whether this is a local execution
            **kwargs: Additional keyword arguments
        """
        try:
            if "system_prompt" in kwargs:
                # Create new agent with updated system prompt
                llm_config = self.task.tools_config.llm_agent.llm_config
                self.llm_agent = get_llm_agent(
                    model=llm_config.model,
                    temperature=llm_config.temperature,
                    max_tokens=llm_config.max_tokens or 100,
                    system_prompt=kwargs["system_prompt"],
                    functions=llm_config.functions,
                    provider_config=llm_config.provider_config
                )
                
            # Set any task-specific prompt configurations
            welcome_message = kwargs.get("agent_welcome_message")
            if welcome_message and hasattr(self.task, "welcome_message"):
                self.task.welcome_message = welcome_message
                
        except Exception as e:
            logger.error(f"Failed to load prompt: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")