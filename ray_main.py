import gradio as gr
import os
import json
from typing import AsyncIterator,  Union, Dict
import aiohttp
from collections import namedtuple

from ray.serve.gradio_integrations import GradioServer

import logging
from ray import serve
import ray
from ray.serve.gradio_integrations import GradioIngress


PROJECT_NAME = "LLMFrontend"

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
    description = "Large Language Model"
    return title, description

def chatbot():
    title, descrition = get_chatInfo()
    bot = gr.ChatInterface(
        response_message, 
        chatbot=gr.Chatbot(height=500),
        textbox=gr.Textbox(
            placeholder="Hi there, I'm an AI assistant powered by Large language Models. How can I help?", 
            container=False, 
            scale=17,
            lines=5,
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


std_logger = logging.getLogger("ray.serve")
route_prefix = "/frontend"


@serve.deployment(route_prefix=route_prefix, name=PROJECT_NAME)
class LLMFrontend(GradioIngress):
    def __init__(self, builder):
        std_logger.setLevel(logging.ERROR)
        blocks = builder()
        super().__init__(lambda: blocks)

        # Gradio queue will make POST requests to the Gradio application
        # using the public URL, while overriding the authorization
        # headers with its own. This results in the public URL rejecting
        # the connection. This is a hacky workaround to set the URL
        # the queue will use to localhost.
        def noop(*args, **kwargs):
            pass

        # Get the port the serve app is running on
        controller = ray.serve.context.get_global_client()._controller
        port = ray.get(controller.get_http_config.remote()).port

        blocks._queue.set_url(f"http://localhost:{port}{route_prefix}/")
        blocks._queue.set_url = noop


app = LLMFrontend.options(
    ray_actor_options={
        "num_cpus": 1,
        "runtime_env": {
            "env_vars": {
                k: v
                for k, v in os.environ.items()
            }
        },
    },
).bind(chatbot)

if __name__ == "__main__":
    ray.init(ignore_reinit_error=True)
    chatbot().launch(show_error=True)

# app = GradioServer.options(
#     num_replicas=1,
#     ray_actor_options={"num_cpus": 1}
# ).bind(
#     chatbot
# )
