"""
Inference endpoint — the core of the Model Service.

Accepts a GenerateRequest, runs it through the ModelManager (which handles
model selection and fallback), and returns a GenerateResponse.
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from model_service.app.dependencies import get_model_manager
from model_service.app.services.model_manager import ModelManager
from shared.schemas import GenerateRequest, GenerateResponse

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
    request: GenerateRequest,
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
    """

    async def event_generator():
        try:
            async for token in model_manager.generate_stream(
                prompt=request.prompt,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system_prompt=request.system_prompt,
            ):
                # json.dumps escapes newlines (\n -> \\n), carriage returns,
                # backslashes, and double quotes. The result is always a
                # single-line JSON string literal, safe to inline in SSE.
                yield f"data: {json.dumps(token)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: [ERROR] {str(exc)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
