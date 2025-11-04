"""
A simple conversational AI assistant using a local model.
"""
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import asyncio

class Assistant:
    def __init__(self):
        """Initialize the AI Assistant"""
        print("Initializing the model (this may take a minute)...")
        
        # Load tokenizer and model
        model_name = "microsoft/DialoGPT-small"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(model_name)
        
        # Initialize conversation history
        self.chat_history_ids = None
        
        print("Model loaded successfully!")

    def reset_conversation(self):
        """Reset the conversation history"""
        self.chat_history_ids = None

    async def chat(self, message: str) -> str:
        """Process a message and return the response"""
        try:
            # Encode user input
            new_input_ids = self.tokenizer.encode(message + self.tokenizer.eos_token, return_tensors='pt')

            # Append to chat history if it exists
            bot_input_ids = torch.cat([self.chat_history_ids, new_input_ids], dim=-1) if self.chat_history_ids is not None else new_input_ids

            # Generate response
            chat_history_ids = await asyncio.to_thread(
                self.model.generate,
                bot_input_ids,
                max_length=1000,
                pad_token_id=self.tokenizer.eos_token_id,
                no_repeat_ngram_size=3,
                do_sample=True,
                top_k=100,
                top_p=0.7,
                temperature=0.8
            )

            # Save chat history
            self.chat_history_ids = chat_history_ids

            # Decode and return the response
            response = self.tokenizer.decode(chat_history_ids[:, bot_input_ids.shape[-1]:][0], skip_special_tokens=True)
            return response.strip()

        except Exception as e:
            # Reset conversation on error
            self.reset_conversation()
            return f"I apologize, but I encountered an error. Let's start fresh - how can I help you?"

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

            # Reset conversation if it gets too long to prevent errors
            if assistant.chat_history_ids is not None and assistant.chat_history_ids.shape[1] > 100:
                assistant.reset_conversation()

        except KeyboardInterrupt:
            print("\n\nAssistant: Goodbye! Have a great day!")
            break
        except Exception as e:
            print(f"\nAn error occurred. Starting fresh...")
            assistant.reset_conversation()

if __name__ == "__main__":
    asyncio.run(run_assistant())