"""
Inference endpoint — the core of the Model Service.

Accepts a GenerateRequest, runs it through the ModelManager (which handles
model selection and fallback), and returns a GenerateResponse.
"""

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from model_service.app.dependencies import get_model_manager
from model_service.app.services.model_manager import ModelManager
from shared.logging import get_logger
from shared.schemas import GenerateRequest, GenerateResponse

logger = get_logger(__name__)
router = APIRouter()


@router.post("/inference", response_model=GenerateResponse)
async def run_inference(
    request: GenerateRequest,
    model_manager: ModelManager = Depends(get_model_manager),
):
    """Generate text from a prompt using the configured LLM.

    The ModelManager handles:
      - Model selection (client override or default)
      - Fallback to secondary model on failure
      - Latency tracking and logging
    """
    result = await model_manager.generate(
        prompt=request.prompt,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        system_prompt=request.system_prompt,
    )

    return GenerateResponse(
        text=result["text"],
        model=result["model"],
        usage=result["usage"],
        latency_ms=result["latency_ms"],
    )


@router.post("/inference/stream")
async def run_inference_stream(
    http_request: Request,
    body: GenerateRequest,
    model_manager: ModelManager = Depends(get_model_manager),
):
    """Stream generated text token-by-token via Server-Sent Events.

    Returns a text/event-stream response. Each token is JSON-encoded so that
    embedded \\n / \\r / quotes inside the token don't collide with the SSE
    framing protocol (which uses \\n as the field/message delimiter).

    Wire format:
        data: "<json-encoded token>"\\n\\n    # e.g.  data: "### Heading\\n\\n"
        data: [DONE]\\n\\n                    # sentinel, plain string
        data: [ERROR] <message>\\n\\n         # error sentinel, plain string

    The client must JSON.parse() each non-sentinel payload to recover the
    real string (with its newlines, tabs, quotes, etc. intact).

    Client-disconnect handling
    --------------------------
    If the downstream HTTP client (the API gateway in our topology, or any
    direct caller) goes away mid-stream, we stop pulling tokens from Groq
    and return. This prevents paying for tokens the client will never see.

    Two things cooperate:
      1. An explicit `await http_request.is_disconnected()` check between
         tokens. Starlette sets this flag when it observes the ASGI
         `http.disconnect` message, which uvicorn emits on TCP FIN from
         the upstream peer.
      2. `except Exception` — NOT `except BaseException`. In Python 3.8+
         `asyncio.CancelledError` is a BaseException subclass, so it
         deliberately skips this handler and propagates up, which lets
         the Starlette runtime cancel the outer task and close the
         Groq async iterator cleanly.
    """

    async def event_generator():
        tokens_sent = 0
        try:
            async for token in model_manager.generate_stream(
                prompt=body.prompt,
                model=body.model,
                max_tokens=body.max_tokens,
                temperature=body.temperature,
                system_prompt=body.system_prompt,
            ):
                # Poll before yielding. is_disconnected() is cheap: it just
                # peeks at the already-buffered ASGI message queue and
                # caches the result once set.
                if await http_request.is_disconnected():
                    logger.info(
                        "stream_aborted",
                        reason="client_disconnected",
                        tokens_sent=tokens_sent,
                        model=body.model,
                    )
                    return  # Exit the generator; Groq iterator is cancelled by GC + task cancellation
                yield f"data: {json.dumps(token)}\n\n"
                tokens_sent += 1
            yield "data: [DONE]\n\n"
            logger.info("stream_completed", tokens_sent=tokens_sent, model=body.model)
        except Exception as exc:  # noqa: BLE001 — intentional: exclude BaseException/CancelledError
            logger.exception("stream_error", tokens_sent=tokens_sent, model=body.model)
            yield f"data: [ERROR] {str(exc)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
