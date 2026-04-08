"""Tests for the markdown Jinja2 filter defined in app/templates_config.py."""
import pytest

from app.templates_config import _markdown_filter


class TestMarkdownFilter:
    def test_basic_paragraph(self):
        result = _markdown_filter("Hello world")
        assert "<p>Hello world</p>" in result

    def test_empty_string_returns_empty(self):
        assert _markdown_filter("") == ""

    def test_none_like_falsy_returns_empty(self):
        # The filter checks `if not value`
        assert _markdown_filter(None) == ""

    def test_bold(self):
        result = _markdown_filter("**bold**")
        assert "<strong>bold</strong>" in result

    def test_italic(self):
        result = _markdown_filter("*italic*")
        assert "<em>italic</em>" in result

    def test_heading(self):
        result = _markdown_filter("# Title")
        assert "<h1>Title</h1>" in result

    def test_unordered_list(self):
        result = _markdown_filter("- item one\n- item two")
        assert "<ul>" in result
        assert "<li>item one</li>" in result
        assert "<li>item two</li>" in result

    def test_ordered_list(self):
        result = _markdown_filter("1. first\n2. second")
        assert "<ol>" in result
        assert "<li>first</li>" in result

    def test_code_inline(self):
        result = _markdown_filter("`code`")
        assert "<code>code</code>" in result

    def test_table_extension(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = _markdown_filter(md)
        assert "<table>" in result
        assert "<th>A</th>" in result

    def test_newline_becomes_br(self):
        """nl2br extension should turn single newlines into <br>."""
        result = _markdown_filter("line one\nline two")
        assert "<br" in result

    def test_xss_script_tag_stripped(self):
        result = _markdown_filter("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "alert" not in result

    def test_xss_event_handler_stripped(self):
        result = _markdown_filter('<a href="#" onclick="evil()">click</a>')
        assert "onclick" not in result

    def test_xss_javascript_href_stripped(self):
        result = _markdown_filter("[click me](javascript:alert(1))")
        # The href with javascript: should be stripped by nh3
        assert "javascript:" not in result

    def test_safe_link_preserved(self):
        result = _markdown_filter("[DnD](https://example.com)")
        # nh3 adds rel="noopener noreferrer" automatically for security
        assert 'href="https://example.com"' in result
        assert ">DnD</a>" in result

    def test_blockquote(self):
        result = _markdown_filter("> a quote")
        assert "<blockquote>" in result

    def test_fenced_code_block(self):
        md = "```\nsome code\n```"
        result = _markdown_filter(md)
        assert "<pre>" in result
        assert "<code>" in result
