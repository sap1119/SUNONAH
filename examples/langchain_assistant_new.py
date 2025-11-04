"""
A simple conversational AI assistant using LangChain.
"""
from typing import List, Optional
import asyncio
import os
from dotenv import load_dotenv

# LangChain imports
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import StreamingStdOutCallbackHandler

# Load environment variables
load_dotenv()

# Verify OpenAI API key is set
if not os.getenv("OPENAI_API_KEY"):
    raise EnvironmentError("Please set OPENAI_API_KEY environment variable")

class Assistant:
    def __init__(self, model_name: str = "gpt-3.5-turbo", temperature: float = 0.7):
        """Initialize the AI Assistant with specified parameters.
        
        Args:
            model_name: The name of the OpenAI model to use
            temperature: Controls randomness in responses (0.0 to 1.0)
        """
        # Initialize message history
        self.messages: List[BaseMessage] = [
            SystemMessage(content=(
                "You are a helpful AI assistant. "
                "You provide clear, accurate, and engaging responses."
            ))
        ]
        
        # Create the language model with streaming
        self.llm = ChatOpenAI(
            streaming=True,
            callbacks=[StreamingStdOutCallbackHandler()],
            temperature=temperature,
            model=model_name
        )
        
        # Create the chat prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful AI assistant. You provide clear, accurate, and engaging responses."),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])
        
        # Create the chain
        self.chain = self.prompt | self.llm | StrOutputParser()

    async def chat(self, message: str) -> str:
        """Process a message and return the response"""
        try:
            # Add user message to history
            self.messages.append(HumanMessage(content=message))
            
            # Get response from the chain
            response = await self.chain.ainvoke({
                "history": self.messages[1:],  # Exclude system message
                "input": message
            })
            
            # Add assistant's response to history
            self.messages.append(AIMessage(content=response))
            
            return response.strip()
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"\n{error_msg}")
            return error_msg

async def run_assistant():
    """Run the interactive chat assistant"""
    # Initialize the assistant
    assistant = Assistant()

    print("Assistant: Hello! I'm your AI assistant. How can I help you today?")

    while True:
        try:
            # Get user input
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ["exit", "quit", "bye"]:
                print("\nAssistant: Goodbye! Have a great day!")
                break

            # Get assistant response
            print("\nAssistant: ", end="", flush=True)
            await assistant.chat(user_input)

        except KeyboardInterrupt:
            print("\n\nAssistant: Goodbye! Have a great day!")
            break
        except Exception as e:
            print(f"\nFatal error: {str(e)}")
            break

if __name__ == "__main__":
    asyncio.run(run_assistant())