"""Tests for the ThinkingFilter that hides <thinking> reasoning in live chat."""

import sys

import pytest

from conftest import load_module, CS, APP


@pytest.fixture
def TF(monkeypatch):
    monkeypatch.delenv("ACME_FRONTEND_MOCK", raising=False)
    sys.path.insert(0, str(CS))
    sys.path.insert(0, str(APP))
    fe = load_module(CS / "frontend" / "frontend.py", "cs_frontend_tf_test")
    return fe.ThinkingFilter


def _run(TF, chunks):
    f = TF()
    out = "".join(f.feed(c) for c in chunks)
    return out + f.flush()


def test_strips_single_thinking_block(TF):
    text = "<thinking>internal</thinking>Hello there."
    assert _run(TF, [text]) == "Hello there."


def test_strips_multiple_blocks(TF):
    text = "<thinking>a</thinking>The plan <thinking>b</thinking>is $60."
    assert _run(TF, [text]) == "The plan is $60."


def test_strips_tag_split_across_chunks(TF):
    # The opening/closing tags are split across streaming chunks.
    chunks = ["<think", "ing>secret re", "asoning</thin", "king>Visible ", "answer"]
    assert _run(TF, chunks) == "Visible answer"


def test_strips_response_wrapper_tags(TF):
    text = "<response>The answer is 42.</response>"
    assert _run(TF, [text]) == "The answer is 42."


def test_plain_text_passes_through(TF):
    text = "Just a normal reply with no tags."
    assert _run(TF, [text]) == text


def test_thinking_then_text_char_by_char(TF):
    text = "<thinking>x</thinking>OK"
    assert _run(TF, list(text)) == "OK"
