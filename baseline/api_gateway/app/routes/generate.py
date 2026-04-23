"""
Text generation endpoint — proxies requests to the Model Service.

The gateway doesn't perform inference itself. It validates the request,
adds observability headers (request_id), and forwards to the model service.
This is the API Gateway pattern: a single entry point that routes, validates,
and decorates requests before they reach backend services.
"""

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api_gateway.app.dependencies import get_model_client, get_settings
from shared.http_client import ServiceClient
from shared.logging import get_logger
from shared.schemas import GenerateRequest, GenerateResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["generation"])


@router.post("/generate", response_model=GenerateResponse)
async def generate_text(
    request: GenerateRequest,
    model_client: ServiceClient = Depends(get_model_client),
):
    """Generate text from a prompt.

    Proxies the request to the Model Service which handles model selection,
    Groq API calls, and fallback logic.
    """
    result = await model_client.post(
        "/inference",
        json=request.model_dump(),
    )
    return GenerateResponse(**result)


@router.post("/generate/stream")
async def generate_text_stream(
    http_request: Request,
    body: GenerateRequest,
    settings=Depends(get_settings),
):
    """Stream generated text token-by-token via Server-Sent Events.

    Proxies the SSE stream from the Model Service to the client.
    Uses a raw httpx streaming request since ServiceClient expects JSON.

    Client-disconnect handling
    --------------------------
    When the browser closes the tab (or calls AbortController.abort()), we
    see an ASGI `http.disconnect` on our downstream socket. We must then
    break out of the byte-proxy loop — which lets httpx's context manager
    close the upstream (gateway→model_service) TCP connection. model_service
    then sees its own `is_disconnected()` go true and stops pulling tokens
    from Groq.

    Without this check, the gateway would happily keep reading bytes from
    model_service (which would keep generating against Groq) long after
    the browser gave up — burning tokens nobody will ever see.
    """

    async def proxy_stream():
        bytes_proxied = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            async with client.stream(
                "POST",
                f"{settings.model_service_url}/inference/stream",
                json=body.model_dump(),
            ) as response:
                async for chunk in response.aiter_bytes():
                    # Bail out the moment the browser-facing connection dies.
                    # Exiting this `async for` + the `async with` above makes
                    # httpx close the upstream socket, which is what signals
                    # model_service to stop generation.
                    if await http_request.is_disconnected():
                        logger.info(
                            "proxy_stream_aborted",
                            reason="client_disconnected",
                            bytes_proxied=bytes_proxied,
                        )
                        return
                    bytes_proxied += len(chunk)
                    yield chunk
        logger.info("proxy_stream_completed", bytes_proxied=bytes_proxied)

    return StreamingResponse(
        proxy_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
