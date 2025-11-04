"""
An improved conversational AI assistant using Microsoft's DialoGPT model.
Includes better response filtering and padding handling.
"""
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList, NoRepeatNGramLogitsProcessor
import torch
import asyncio
import re

class ResponseFilter:
    """Filter and clean model responses"""
    @staticmethod
    def clean_response(text: str) -> str:
        # Remove any warning messages
        if "A decoder-only architecture" in text:
            text = text.split("tokenizer.")[-1].strip()
        
        # Basic cleanups
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        text = text.strip()
        
        # Remove incomplete sentences at the end
        if text and text[-1] not in '.!?':
            last_sentence = text.split('.')[-1]
            text = text[:-len(last_sentence)].strip()
        
        return text or "I'm not sure how to respond to that."

class Assistant:
    def __init__(self):
        """Initialize the AI Assistant with DialoGPT-medium"""
        print("Initializing the model (this may take a minute)...")
        
        # Load model and tokenizer
        model_name = "microsoft/DialoGPT-medium"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(model_name)
        
        # Critical: Set padding settings correctly
        self.tokenizer.padding_side = 'left'
        self.tokenizer.pad_token = self.tokenizer.eos_token
        
        # Initialize conversation state
        self.conversation_history = []
        print("Model loaded successfully!")

    def _prepare_input(self, message: str) -> torch.Tensor:
        """Prepare input with proper history handling"""
        # Add message to history (keep last 5 turns)
        self.conversation_history.append(message)
        if len(self.conversation_history) > 10:  # 5 turns (user + assistant)
            self.conversation_history = self.conversation_history[-10:]
            
        # Join history with EOS token
        history_text = self.tokenizer.eos_token.join(self.conversation_history)
        
        # Encode with proper padding
        inputs = self.tokenizer.encode(
            history_text + self.tokenizer.eos_token,
            return_tensors='pt',
            padding=True,
            truncation=True,
            max_length=1024
        )
        
        return inputs

    async def _generate_response(self, input_ids: torch.Tensor) -> str:
        """Generate response using optimized parameters"""
        try:
            # Setup generation config
            no_repeat_processor = NoRepeatNGramLogitsProcessor(3)
            processors = LogitsProcessorList([no_repeat_processor])
            
            # Generate response
            output_ids = await asyncio.to_thread(
                self.model.generate,
                input_ids,
                max_length=input_ids.shape[-1] + 50,  # Allow for decent response length
                pad_token_id=self.tokenizer.eos_token_id,
                logits_processor=processors,
                do_sample=True,
                top_k=50,
                top_p=0.92,
                temperature=0.85,
                num_return_sequences=1,
                repetition_penalty=1.2,
                length_penalty=1.0,
                use_cache=True
            )
            
            # Extract only the new tokens (response)
            response_ids = output_ids[:, input_ids.shape[-1]:]
            response = self.tokenizer.decode(response_ids[0], skip_special_tokens=True)
            
            return ResponseFilter.clean_response(response)
            
        except Exception as e:
            print(f"Generation error: {str(e)}")
            return "I encountered an error in processing. Let's continue our conversation."

    async def chat(self, message: str) -> str:
        """Process a message and return a response"""
        try:
            # Check for special commands
            message = message.strip()
            if message.lower() in ['reset', 'clear', 'restart']:
                self.reset_conversation()
                return "Conversation reset. How can I help you?"
            
            # Generate and return response
            input_ids = self._prepare_input(message)
            response = await self._generate_response(input_ids)
            
            # Add response to history
            self.conversation_history.append(response)
            
            return response
            
        except Exception as e:
            self.reset_conversation()
            return f"I encountered an error. Let's start fresh! Error: {str(e)}"

    def reset_conversation(self):
        """Reset the conversation history"""
        self.conversation_history = []

async def run_assistant():
    """Run the interactive chat assistant"""
    assistant = Assistant()
    print("\nAssistant: Hello! I'm your AI assistant. How can I help you today?")

    while True:
        try:
            # Get user input
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ["exit", "quit", "bye"]:
                print("\nAssistant: Goodbye! Have a great day!")
                break

            # Get assistant response
            print("\nAssistant: ", end="", flush=True)
            response = await assistant.chat(user_input)
            print(response)

        except KeyboardInterrupt:
            print("\n\nAssistant: Goodbye! Have a great day!")
            break
        except Exception as e:
            print(f"\nAn error occurred: {str(e)}")
            continue

if __name__ == "__main__":
    asyncio.run(run_assistant())