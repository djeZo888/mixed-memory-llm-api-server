"""Narrow compatibility repairs for the pinned Flash tool runtime.

llguidance 0.7.30 treats HF added tokens as special even when their authoritative
AddedToken.special flag is false. GLM's XML tool markers are such tokens. Keep
the original tokenizer's bytes and encoder, correcting only that classification
inside the grammar matcher; chat/tokenize rendering remains untouched.
"""
from __future__ import annotations

import functools
import hashlib
import importlib.metadata
from pathlib import Path


GUIDANCE_SOURCE_SHA256 = '331893a2c07343b5a416b27e4ede5ad87c03852117267565188d090948318ac1'
CHAT_SOURCE_SHA256 = '50e16cef7f5035b3797c9c421697ce5401ad3857e49fd9e11fa469253f994581'


def repair_llguidance_tokenizer(native, hf_tokenizer, *, n_vocab=None):
    """Preserve all token bytes/IDs while honoring non-special added tokens."""
    from llguidance import LLTokenizer, TokenizerWrapper

    added = hf_tokenizer.added_tokens_decoder
    repaired_ids = {int(i) for i, token in added.items()
                    if not token.special and native.is_special_token(int(i))}
    if not repaired_ids:
        return native

    class Adapter:
        eos_token_id = native.eos_token
        bos_token_id = getattr(hf_tokenizer, 'bos_token_id', None)
        tokens = [native.decode_bytes([i]) for i in range(native.vocab_size)]
        # Preserve native classification for every other token, including gaps
        # between tokenizer vocabulary and model output vocabulary.
        special_token_ids = [i for i in range(native.vocab_size)
                             if native.is_special_token(i) and i not in repaired_ids]

        def __call__(self, value):
            return hf_tokenizer.encode(value, add_special_tokens=False)

    fixed = LLTokenizer(TokenizerWrapper(Adapter()), n_vocab=n_vocab,
                        eos_token=native.eos_token)
    if any(fixed.is_special_token(i) or
           fixed.decode_bytes([i]) != native.decode_bytes([i])
           for i in repaired_ids):
        raise RuntimeError('flash_tool_tokenizer_repair_failed')
    return fixed


def install_grammar_patch(backend):
    original = backend._create_llguidance_tokenizer
    if getattr(original, '_flash_added_token_repair', False):
        return

    @functools.wraps(original)
    def create(tokenizer, n_vocab):
        native = original(tokenizer, n_vocab)
        return repair_llguidance_tokenizer(native, tokenizer, n_vocab=n_vocab)

    create._flash_added_token_repair = True
    backend._create_llguidance_tokenizer = create


def install_completion_patch(serving_class):
    original = serving_class._check_for_unstreamed_tool_args
    if getattr(original, '_flash_incomplete_tool_guard', False):
        return

    @functools.wraps(original)
    def check(self, parser, content, request, index):
        detector = getattr(parser, 'detector', parser)
        calls = getattr(detector, 'prev_tool_call_arr', None)
        # A lone <tool_call> creates an empty tracking slot. The native flush
        # otherwise turns its default arguments={} into a phantom unnamed call.
        # ValueError is converted by the native stream handler to an SSE error.
        if self.tool_call_parser == 'glm47' and calls and not calls[-1].get('name'):
            raise ValueError('flash_incomplete_tool_call_without_name')
        return original(self, parser, content, request, index)

    check._flash_incomplete_tool_guard = True
    serving_class._check_for_unstreamed_tool_args = check


def install():
    """Install before native grammar construction in API and scheduler processes."""
    from sglang.srt.constrained import llguidance_backend
    from sglang.srt.entrypoints.openai import serving_chat

    if importlib.metadata.version('llguidance') != '0.7.30':
        raise RuntimeError('flash_tool_llguidance_version_mismatch')
    for module, digest in [(llguidance_backend, GUIDANCE_SOURCE_SHA256),
                           (serving_chat, CHAT_SOURCE_SHA256)]:
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != digest:
            raise RuntimeError('flash_tool_native_source_mismatch')
    install_grammar_patch(llguidance_backend)
    install_completion_patch(serving_chat.OpenAIServingChat)
