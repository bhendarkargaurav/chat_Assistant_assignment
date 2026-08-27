"""Sanitization for LLM-generated HTML/CSS artifacts.

LLM output is untrusted input: it is generated from transcript text and user
messages, both of which an attacker can influence. Everything that ends up in
an artifact goes through :func:`sanitize_html_document` before it is persisted,
so stored artifacts are safe by construction rather than at render time.

Strategy:
1. Drop executable/embedding elements together with their text content, so
   nothing leaks through as inert-but-confusing text.
2. Extract ``<style>`` blocks (bleach escapes their contents, and CSS needs its
   own grammar-aware pass anyway).
3. Run the rest through bleach with a tag/attribute allowlist, which drops
   remaining unknown tags, event handlers and dangerous URL schemes.
4. Sanitize each stylesheet with tinycss2, dropping at-rules and declarations
   that can fetch or execute anything, then re-insert them.
"""

import logging
import re

import bleach
import tinycss2
from bleach.css_sanitizer import CSSSanitizer

from backend.app.exceptions import ArtifactError

logger = logging.getLogger(__name__)

ALLOWED_TAGS = {
    "a", "abbr", "article", "aside", "b", "blockquote", "br", "caption", "cite",
    "code", "col", "colgroup", "dd", "div", "dl", "dt", "em", "figcaption",
    "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "i",
    "img", "li", "main", "mark", "nav", "ol", "p", "pre", "section", "small",
    "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th",
    "thead", "time", "tr", "u", "ul",
}

ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "style", "title", "role", "aria-label"],
    "a": ["href", "target", "rel"],
    "img": ["src", "alt", "width", "height", "loading"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
    "time": ["datetime"],
}

# No `data:` — `data:text/html` in an href is an XSS vector, and artifacts have
# no need to inline binary payloads.
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

ALLOWED_CSS_AT_RULES = {"media", "supports", "keyframes", "-webkit-keyframes", "font-face"}

# Anything that can load or execute: url()/image-set() fetches, IE expressions,
# XBL bindings and @import.
_DANGEROUS_CSS = re.compile(
    r"(expression\s*\(|javascript\s*:|vbscript\s*:|behavior\s*:|-moz-binding|@import|url\s*\()",
    re.IGNORECASE,
)

_DROPPED_ELEMENTS = (
    "script", "iframe", "object", "embed", "applet", "noscript", "template",
    "form", "svg", "math", "link", "meta", "base",
)
_DROP_WITH_CONTENT = re.compile(
    r"<\s*(" + "|".join(_DROPPED_ELEMENTS) + r")\b[^>]*>.*?<\s*/\s*\1\s*>|"
    r"<\s*(?:" + "|".join(_DROPPED_ELEMENTS) + r")\b[^>]*/?>",
    re.IGNORECASE | re.DOTALL,
)

_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.IGNORECASE | re.DOTALL)
_STYLE_PLACEHOLDER = "__LENNY_STYLE_BLOCK_{index}__"

# Defaults to bleach's allowlist of safe CSS properties.
_CSS_SANITIZER = CSSSanitizer(allowed_svg_properties=[])


def sanitize_css(css: str) -> str:
    """Return CSS with unsafe at-rules and declarations removed."""
    rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
    kept: list[str] = []

    for rule in rules:
        if rule.type == "error":
            continue
        if rule.type == "at-rule":
            name = (rule.lower_at_keyword or "").lower()
            if name not in ALLOWED_CSS_AT_RULES:
                logger.warning("Dropped disallowed CSS at-rule: @%s", name)
                continue
        serialized = rule.serialize()
        if _DANGEROUS_CSS.search(serialized):
            logger.warning("Dropped CSS rule containing an unsafe construct")
            continue
        kept.append(serialized)

    return "\n".join(part.strip() for part in kept if part.strip())


def sanitize_html_document(html: str) -> str:
    """Sanitize an HTML fragment or document, preserving safe ``<style>`` CSS."""
    if not html or not html.strip():
        return ""

    html = _DROP_WITH_CONTENT.sub("", html)
    styles: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        styles.append(match.group(1))
        return _STYLE_PLACEHOLDER.format(index=len(styles) - 1)

    stripped = _STYLE_BLOCK.sub(_stash, html)

    cleaned = bleach.clean(
        stripped,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=_CSS_SANITIZER,
        strip=True,
        strip_comments=True,
    )

    for index, raw_css in enumerate(styles):
        safe_css = sanitize_css(raw_css)
        placeholder = _STYLE_PLACEHOLDER.format(index=index)
        replacement = f"<style>\n{safe_css}\n</style>" if safe_css else ""
        cleaned = cleaned.replace(placeholder, replacement)

    return cleaned.strip()


_UNSAFE_MARKERS = re.compile(
    r"<\s*(?:script|iframe|object|embed|applet|form|link|base)\b"
    r"|\son[a-z]+\s*="
    r"|javascript\s*:"
    r"|vbscript\s*:"
    r"|data\s*:\s*text/html",
    re.IGNORECASE,
)


def assert_safe_html(content: str) -> None:
    """Fail closed if HTML about to be stored or served still looks dangerous.

    ``sanitize_html_document`` is the real control; this is the cheap invariant
    check that runs on every write and read so a sanitizer regression cannot
    silently ship stored XSS.
    """
    match = _UNSAFE_MARKERS.search(content)
    if match:
        logger.error("Refusing unsafe HTML artifact (matched %r)", match.group(0))
        raise ArtifactError(
            "HTML artifact failed the safety check and was rejected", status_code=422
        )


def strip_html(text: str) -> str:
    """Remove every tag — used when embedding LLM text into markdown."""
    return bleach.clean(text, tags=set(), attributes={}, strip=True)
