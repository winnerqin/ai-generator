"""Flask-facing compatibility layer for the legacy generator UI."""

from __future__ import annotations

from flask import Response, request, session, stream_with_context

from app.services.generation_config import GenerationRequest
from app.services.generation_flow import collect_non_stream_response, stream_generated_images
from app.services.generation_storage import (
    get_user_output_folder,
    save_uploaded_reference_images,
)
from app.services.generation_stream import (
    create_channel,
    finalize_channel,
    get_channel,
    publish_event,
    stream_from_channel,
)
from app.utils import ApiResponse


def _parse_generation_request() -> GenerationRequest:
    return GenerationRequest(
        user_id=session.get("user_id"),
        project_id=session.get("current_project_id"),
        prompt=request.form.get("prompt", "").strip(),
        aspect_ratio=request.form.get("aspect_ratio", "9:16"),
        resolution=request.form.get("resolution", "2k"),
        generate_mode=request.form.get("generate_mode", "single"),
        num_images=int(request.form.get("num_images", 4)),
        image_style=request.form.get("image_style", "").strip(),
        seed=int(request.form.get("seed", 0)),
        output_filename=request.form.get("output_filename", "").strip(),
        stream=request.form.get("stream", "true").lower() == "true",
    )


def generate_legacy_request():
    generation_request = _parse_generation_request()
    if not generation_request.prompt:
        return ApiResponse.bad_request("\u8bf7\u8f93\u5165\u63d0\u793a\u8bcd")

    image_urls = list(request.form.getlist("sample_image_urls"))
    image_urls.extend(
        save_uploaded_reference_images(
            generation_request.user_id,
            generation_request.project_id,
            request.files.getlist("images"),
        )
    )

    if generation_request.stream:
        channel = create_channel(generation_request.user_id)

        def worker() -> None:
            event_index = 0
            try:
                for payload in stream_generated_images(generation_request, image_urls):
                    publish_event(channel, payload, event_index)
                    event_index += 1
            finally:
                finalize_channel(channel)

        import threading

        threading.Thread(target=worker, daemon=True).start()
        return Response(
            stream_with_context(stream_from_channel(channel, 0)),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Generation-Id": channel["id"],
            },
        )

    return collect_non_stream_response(generation_request, image_urls)


def resume_legacy_generation_stream():
    generation_id = request.args.get("generation_id", "").strip()
    from_index = request.args.get("from", "0").strip()
    if not generation_id:
        return ApiResponse.bad_request("\u7f3a\u5c11 generation_id")
    try:
        start_index = max(0, int(from_index or "0"))
    except ValueError:
        return ApiResponse.bad_request("\u65e0\u6548\u7684 from \u53c2\u6570")

    channel = get_channel(generation_id)
    if not channel:
        return ApiResponse.not_found("\u5bf9\u5e94\u7684\u751f\u6210\u901a\u9053\u4e0d\u5b58\u5728")

    if channel.get("user_id") != session.get("user_id"):
        return ApiResponse.forbidden("\u65e0\u6743\u8bbf\u95ee\u8be5\u751f\u6210\u901a\u9053")

    return Response(
        stream_with_context(stream_from_channel(channel, start_index)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = [
    "generate_legacy_request",
    "resume_legacy_generation_stream",
    "get_user_output_folder",
]
