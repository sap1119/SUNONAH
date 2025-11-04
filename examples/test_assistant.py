import asyncio
from bolna.assistant import Assistant


async def main():
    assistant = Assistant(name="test_agent")

    # Configure LLM with OpenAI
    llm_config = {
        "provider": "openai",
        "model": "gpt-3.5-turbo",
        "temperature": 0.3,
    }

    # Build a simple text-only pipeline
    assistant.add_task(
        task_type="conversation",
        llm_agent=llm_config,
        enable_textual_input=True,  # Enable text input
    )

    # Stream results
    async for _, chunk in assistant.execute():
        print(chunk)


if __name__ == "__main__":
    asyncio.run(main())