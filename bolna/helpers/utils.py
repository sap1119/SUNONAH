import time
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def now_ms():
    """Get current timestamp in milliseconds"""
    return int(round(time.time() * 1000))

def create_ws_data_packet(data: Any = None, meta_info: Optional[Dict] = None) -> Dict:
    """Create a WebSocket data packet with metadata.
    
    Args:
        data: The payload data to include in the packet
        meta_info: Optional metadata to include with the packet
        
    Returns:
        Dict containing the formatted WebSocket packet with data, metadata, and timestamp
    """
    return {
        "data": data,
        "meta_info": meta_info or {},
        "timestamp": now_ms()
    }

def convert_to_request_log(arguments_received, meta_info, model, source, direction="request", is_cached=False, run_id=None):
    """Convert request data to log format"""
    try:
        logger.info(f"Converting {direction} to request log")
        logger.info(f"Arguments received: {arguments_received}")
        logger.info(f"Meta info: {meta_info}")
        
        if isinstance(arguments_received, str):
            arguments_received = json.loads(arguments_received)
            
        request_log = {
            "timestamp": now_ms(),
            "direction": direction,
            "source": source,
            "model": model,
            "is_cached": is_cached,
            "run_id": run_id
        }
        
        if meta_info:
            request_log.update({
                "sequence_id": meta_info.get("sequence_id"),
                "turn_id": meta_info.get("turn_id"),
                "session_id": meta_info.get("session_id")
            })
            
        request_log.update(arguments_received)
        return request_log
    except Exception as e:
        logger.error(f"Error converting to request log: {str(e)}")
        return None

def compute_function_pre_call_message(language, function_name, pre_call_message=None):
    """Compute pre-call message for function calls"""
    if pre_call_message:
        return pre_call_message
        
    # Default messages in different languages
    messages = {
        "en": {
            "default": "Let me check that for you.",
            "weather": "Let me check the weather for you.",
            "news": "Let me fetch the latest news.",
            "search": "Let me search for that information.",
        },
        "hi": {
            "default": "मैं आपके लिए यह जाँच करता हूं।",
            "weather": "मैं आपके लिए मौसम की जानकारी देखता हूं।",
            "news": "मैं आपके लिए ताज़ा खबरें लाता हूं।",
            "search": "मैं इस जानकारी को खोजता हूं।",
        }
    }
    
    # Default to English if language not supported
    lang_messages = messages.get(language, messages["en"])
    
    # Return function-specific message if available, otherwise default message
    return lang_messages.get(function_name, lang_messages["default"])

def format_messages(messages):
    """Format chat messages for logging and analysis"""
    formatted = []
    for msg in messages:
        if isinstance(msg, dict):
            formatted_msg = {
                "role": msg.get("role", "unknown"),
                "content": msg.get("content", "")
            }
            # Include function call if present
            if "function_call" in msg:
                formatted_msg["function_call"] = msg["function_call"]
            # Include name if present (for function messages)
            if "name" in msg:
                formatted_msg["name"] = msg["name"]
            formatted.append(formatted_msg)
        elif isinstance(msg, str):
            formatted.append({"role": "user", "content": msg})
    return formatted

def update_prompt_with_context(prompt: str, context_data: Optional[Dict[str, Any]] = None) -> str:
    """Update prompt with context data if available.
    
    Args:
        prompt: The original prompt string
        context_data: Optional dictionary of context data to insert into prompt
        
    Returns:
        Updated prompt with context values inserted
    """
    if not context_data:
        return prompt
        
    try:
        # Replace any placeholders in the prompt with context data
        for key, value in context_data.items():
            placeholder = f"{{{key}}}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))
    except Exception as e:
        logger.error(f"Error updating prompt with context: {str(e)}")
        return prompt
        
    return prompt