from enum import Enum


class Intent(str, Enum):
    QA = "qa"
    SHIP30_ESSAY = "ship30_essay"
    ARTIFACT_MARKDOWN = "artifact_markdown"
    ARTIFACT_HTML = "artifact_html"
