# CallAgent.AI

CallAgent.AI is a versatile conversational AI framework that enables natural voice interactions through multiple channels.

## Features

- Voice and text-based conversations
- Multiple LLM providers support
- Various speech-to-text and text-to-speech providers
- Telephony integration (Twilio, Plivo, Exotel)
- Context-aware conversations
- Easy to extend and customize

## Quick Start

1. Install the package:
```bash
pip install bolna
```

2. Set up environment variables:
```bash
cp .env.sample .env
# Edit .env with your API keys
```

3. Run a simple example:
```python
from bolna.assistant import Assistant

assistant = Assistant()
response = assistant.chat("Hello!")
print(response)
```

## Documentation

For detailed documentation, examples, and API reference, visit our documentation site.

## License

This project is licensed under the MIT License - see the LICENSE file for details.