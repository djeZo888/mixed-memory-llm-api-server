"""Text-only H008 tokenization through the pinned native chat preprocessing path.

The launcher must install native authentication around this app. This module
neither creates a listener nor reads credentials, loads weights or dispatches
inference. Final native-image reconciliation is an activation prerequisite.
"""
from __future__ import annotations

import copy
import json

MODEL = 'glm-5.3-flash'
REVISION = 'eb9eb208eb0d988989d07a6a12d0fdeb5f52574a'
CONTEXT = 480000
OUTPUT = 65536
MAX_BODY = 16 * 1024 * 1024


class ContractError(ValueError):
    pass


def normalized_text_request(payload):
    if not isinstance(payload, dict) or payload.get('model') != MODEL:
        raise ContractError('exact_flash_model_required')
    value = copy.deepcopy(payload)
    messages = value.get('messages')
    if not isinstance(messages, list) or not messages:
        raise ContractError('messages_required')
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in {'system', 'user', 'assistant', 'tool'}:
            raise ContractError('text_message_required')
        if message.get('content') is not None and not isinstance(message['content'], str):
            raise ContractError('multimodal_payload_unqualified')
        if any(key in message for key in ('image_url', 'video_url', 'audio', 'input_audio')):
            raise ContractError('multimodal_payload_unqualified')
    if any(key in value for key in ('image_data', 'video_data', 'audio_data', 'modalities')):
        raise ContractError('multimodal_payload_unqualified')
    if value.get('reasoning_effort', 'high') != 'high':
        raise ContractError('high_reasoning_required')
    kwargs = value.get('chat_template_kwargs')
    if kwargs is None:
        kwargs = {}
    if not isinstance(kwargs, dict) or kwargs.get('clear_thinking', True) is not True:
        raise ContractError('clear_thinking_required')
    # Native template options other than the reviewed clear-thinking policy
    # need a new contract; do not let an exact count describe different input.
    if set(kwargs) - {'clear_thinking'}:
        raise ContractError('unreviewed_template_option')
    for field in ('max_tokens', 'max_completion_tokens'):
        if field in value and (type(value[field]) is not int or not 1 <= value[field] <= OUTPUT):
            raise ContractError('output_ceiling_exceeded')
    value['reasoning_effort'] = 'high'
    value['chat_template_kwargs'] = {'clear_thinking': True}
    return value


def count_native(payload, *, request_type, serving_chat):
    """Use exactly the same native tool selection/history/template path as chat."""
    normalized = normalized_text_request(payload)
    request = request_type(**normalized)
    result = serving_chat._process_messages(request, is_multimodal=False)
    ids = result.prompt_ids
    if not isinstance(ids, list) or any(type(token) is not int for token in ids):
        raise ContractError('native_token_ids_unavailable')
    return {'count': len(ids), 'tokenizer_revision': REVISION,
            'template_revision': REVISION, 'context_limit': CONTEXT}


def install_tokenize_route(http_server, request_type):
    """Install before server startup, inside its existing native auth boundary."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    app = http_server.app
    if any(getattr(route, 'path', None) == '/v1/tokenize' for route in app.routes):
        raise ContractError('tokenize_route_already_exists')

    async def tokenize(request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_BODY:
                return JSONResponse({'error': {'code': 'request_too_large'}}, status_code=413)
        try:
            payload = json.loads(data)
            result = count_native(payload, request_type=request_type,
                                  serving_chat=request.app.state.openai_serving_chat)
        except (ValueError, TypeError):
            return JSONResponse({'error': {'code': 'invalid_text_tokenize_request'}}, status_code=400)
        return JSONResponse(result)

    # Resolve Request explicitly: postponed local annotations cannot be resolved
    # by FastAPI against the module namespace without an eager import.
    tokenize.__annotations__['request'] = Request
    app.add_api_route('/v1/tokenize', tokenize, methods=['POST'], include_in_schema=False)
