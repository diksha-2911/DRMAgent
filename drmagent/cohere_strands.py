import os

from strands import Agent
from strands.models.openai import OpenAIModel
from strands_google import use_google, gmail_send, gmail_reply
from dotenv import load_dotenv
load_dotenv()

model = OpenAIModel(
    client_args={
        "api_key": "u0MJYSIOeXSSCG8kAiAEXgNpd0YY2yI0yvg6KCEB",
        "base_url": "https://api.cohere.ai/compatibility/v1",
    },
    model_id="command-a-03-2025",
    # The Compatibility API rejects stream_options; unset the SDK default
    params={"stream_options": None},
)

# agent = Agent(model=model)
# response = agent("Explain tool calling in one sentence.")
# print(response)

# from strands import Agent
# from strands_google import use_google, gmail_send, gmail_reply

agent = Agent(model=model, tools=[use_google, gmail_send, gmail_reply])

# Send an email
agent("Send an email to tanushreetnay@gmail.com saying hello")