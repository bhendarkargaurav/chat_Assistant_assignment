import pytest

from backend.app.exceptions import ArtifactError
from backend.app.services.sanitize import (
    assert_safe_html,
    sanitize_css,
    sanitize_html_document,
)

XSS_VECTORS = [
    "<script>alert('xss')</script><p>ok</p>",
    "<p onclick=\"alert(1)\">ok</p>",
    "<img src=x onerror=alert(1)>",
    "<iframe src=\"https://evil.example\"></iframe><p>ok</p>",
    "<a href=\"javascript:alert(1)\">click</a>",
    "<a href=\"data:text/html;base64,PHNjcmlwdD4=\">click</a>",
    "<object data=\"evil.swf\"></object><p>ok</p>",
    "<form action=\"https://evil.example\"><input name=x></form>",
    "<svg><script>alert(1)</script></svg>",
    "<base href=\"https://evil.example\">",
    "<link rel=stylesheet href=\"https://evil.example/x.css\">",
    "<body background=\"javascript:alert(1)\"><p>ok</p></body>",
]


@pytest.mark.parametrize("payload", XSS_VECTORS)
def test_sanitizer_neutralizes_xss_vectors(payload):
    cleaned = sanitize_html_document(payload)
    assert_safe_html(cleaned)
    assert "alert(1)" not in cleaned
    assert "alert('xss')" not in cleaned


def test_sanitizer_keeps_safe_structure_and_css():
    html = (
        "<!DOCTYPE html><html><head><style>body { color: #111; } "
        "@media (max-width: 600px) { .card { padding: 8px; } }</style></head>"
        "<body><header><h1>Title</h1></header><main><section class=\"card\">"
        "<p style=\"font-weight: 600\">Copy</p>"
        "<a href=\"https://example.com\">link</a></section></main></body></html>"
    )
    cleaned = sanitize_html_document(html)
    assert "<h1>Title</h1>" in cleaned
    assert "color: #111" in cleaned
    assert "@media" in cleaned
    assert 'href="https://example.com"' in cleaned
    assert 'class="card"' in cleaned


def test_css_sanitizer_drops_fetching_and_executing_constructs():
    css = sanitize_css(
        "@import url('https://evil.example/x.css');"
        ".a { background: url(javascript:alert(1)); }"
        ".b { behavior: url(evil.htc); }"
        ".c { width: expression(alert(1)); }"
        ".d { color: red; }"
    )
    assert "@import" not in css
    assert "javascript" not in css
    assert "behavior" not in css
    assert "expression" not in css
    assert ".d" in css


def test_assert_safe_html_rejects_dangerous_content():
    with pytest.raises(ArtifactError):
        assert_safe_html("<p>ok</p><script>alert(1)</script>")
    with pytest.raises(ArtifactError):
        assert_safe_html('<p onmouseover="steal()">ok</p>')


def test_sanitize_empty_input():
    assert sanitize_html_document("") == ""
    assert sanitize_html_document("   ") == ""
