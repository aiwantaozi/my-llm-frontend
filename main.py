import gradio as gr
import os
import json
from typing import AsyncIterator,  Union, Dict
import aiohttp
from collections import namedtuple

env_model = "MODEL_NAME"
env_backend = "BACKEND_URL"
TIMEOUT = (5, 120)

EXAMPLES_QA = [
    "How do I make fried rice? ",
    "What are the 5 best sci fi books? ",
    "What are the best places in the world to visit? ",
    "Which Olympics were held in Australia?",
]

EXAMPLES_IF = [
    "Please describe a beautiful house.",
    "Generate 5 second grade level math problems.",
    "Write a poem about shoes.",
]

async def response_message(message, history):
    model = os.getenv(env_model)
    response=""
    async for response_data in stream(model, message):
        text = _get_text(response_data) or ""
        response = response+text
        yield response
    
def get_chatInfo():
    title = "Seal Deployed Large Language Model Chat"
    description = "Large Language Model Deployed by Seal"
    return title, description

def chatbot():
    title, descrition = get_chatInfo()
    bot = gr.ChatInterface(
        response_message, 
        chatbot=gr.Chatbot(height=500),
        textbox=gr.Textbox(
            placeholder="Hi there, I'm an AI assistant powered by Large Language Models. How can I help?",
            container=False, 
            scale=15,
            lines=4,
            ),
        title=title, 
        description=descrition, 
        examples=EXAMPLES_QA,
        cache_examples=False,
        analytics_enabled=False,
        theme="soft",
    ).queue()
    return bot

class ResponseError(RuntimeError):
    def __init__(self, *args: object, **kwargs) -> None:
        self.response = kwargs.pop("response", None)
        super().__init__(*args)

response = namedtuple("Response", ["text", "status_code"])

async def stream(
    model: str, prompt: str
) -> AsyncIterator[Dict[str, Union[str, float, int]]]:
    """Query LLM and stream response"""
    r = None
    backend = get_backend()
    url = backend + "/chat/completions"

    chunk = b""
    try:
        async with aiohttp.ClientSession(
            raise_for_status=True
        ) as session:
            async with session.post(
                url,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
                timeout=TIMEOUT[-1],
            ) as r:
                async for chunk in r.content:
                    chunk = chunk.replace(b"data: ", b"").strip()
                    if not chunk or chunk == b"[DONE]" or chunk == b"[done]":
                        continue
                    data = json.loads(chunk)
                    if data.get("error"):
                        raise ResponseError(
                            data["error"],
                            response=response(data["error"], r.status),
                        )
                    yield data
    except Exception as e:
        if isinstance(e, ResponseError):
            raise e
        else:
            status = r.status if r else 500
            raise ResponseError(
                str(e), response=response(chunk.decode("utf-8"), status)
            ) from e

def get_backend():
    backend_url = os.getenv(env_backend)
    if not backend_url:
        raise "BACKEND_URL must be set"

    backend_url += "/v1" if not backend_url.endswith("/v1") else ""
    
    print(f"Connecting to backend at: {backend_url}")
    return backend_url

def _get_text(result: dict) -> str:
    if "text" in result["choices"][0]:
        return result["choices"][0]["text"]
    elif "message" in result["choices"][0]:
        return result["choices"][0]["message"]["content"]
    elif "delta" in result["choices"][0]:
        return result["choices"][0]["delta"].get("content", "")

demo = chatbot()

if __name__ == "__main__":
    demo.launch()
