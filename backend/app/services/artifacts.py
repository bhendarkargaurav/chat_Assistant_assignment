import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.models import Artifact, ArtifactKind
from backend.app.exceptions import ArtifactError, NotFoundError, PersistenceError
from backend.app.observability.metrics import METRICS
from backend.app.services.sanitize import assert_safe_html
from backend.app.skills.base import ArtifactDraft, count_words

logger = logging.getLogger(__name__)


class ArtifactService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_from_draft(
        self,
        draft: ArtifactDraft,
        *,
        session_id: UUID | None,
        message_id: UUID | None = None,
        skill: str | None = None,
        commit: bool = True,
    ) -> Artifact:
        """Persist a generated artifact. HTML is re-checked before it is stored."""
        if draft.kind == ArtifactKind.HTML:
            assert_safe_html(draft.content)

        artifact = Artifact(
            session_id=session_id,
            message_id=message_id,
            kind=draft.kind.value,
            title=draft.title or "Untitled artifact",
            content=draft.content,
            skill=skill or draft.metadata.get("skill", "unknown"),
            word_count=count_words(draft.content),
            sources_json=json.dumps(
                [source.model_dump(mode="json") for source in draft.sources]
            ),
            metadata_json=json.dumps(draft.metadata) if draft.metadata else None,
        )
        self.db.add(artifact)
        try:
            if commit:
                self.db.commit()
                self.db.refresh(artifact)
            else:
                self.db.flush()
        except SQLAlchemyError as exc:
            self.db.rollback()
            METRICS.increment("artifact_persistence_failures_total")
            logger.exception("Failed to persist artifact")
            raise PersistenceError(f"Could not persist artifact: {exc}") from exc

        METRICS.increment("artifacts_created_total", kind=artifact.kind)
        logger.info(
            "Persisted artifact %s",
            artifact.id,
            extra={
                "artifact_id": str(artifact.id),
                "artifact_kind": artifact.kind,
                "skill": artifact.skill,
                "word_count": artifact.word_count,
            },
        )
        return artifact

    def get(self, artifact_id: UUID) -> Artifact:
        artifact = self.db.get(Artifact, artifact_id)
        if not artifact:
            raise NotFoundError(f"Artifact {artifact_id} not found")
        return artifact

    def list_artifacts(
        self,
        *,
        session_id: UUID | None = None,
        kind: ArtifactKind | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Artifact]:
        stmt = select(Artifact).order_by(Artifact.created_at.desc())
        if session_id is not None:
            stmt = stmt.where(Artifact.session_id == session_id)
        if kind is not None:
            stmt = stmt.where(Artifact.kind == kind.value)
        stmt = stmt.limit(max(1, min(limit, 200))).offset(max(0, offset))
        return list(self.db.scalars(stmt).all())

    def delete(self, artifact_id: UUID) -> None:
        artifact = self.get(artifact_id)
        try:
            self.db.delete(artifact)
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise PersistenceError(f"Could not delete artifact: {exc}") from exc
        METRICS.increment("artifacts_deleted_total", kind=artifact.kind)

    @staticmethod
    def parse_sources(artifact: Artifact) -> list[dict]:
        if not artifact.sources_json:
            return []
        try:
            payload = json.loads(artifact.sources_json)
        except json.JSONDecodeError:
            logger.warning("Artifact %s has unparsable sources_json", artifact.id)
            return []
        return payload if isinstance(payload, list) else []

    @staticmethod
    def parse_metadata(artifact: Artifact) -> dict:
        if not artifact.metadata_json:
            return {}
        try:
            payload = json.loads(artifact.metadata_json)
        except json.JSONDecodeError:
            logger.warning("Artifact %s has unparsable metadata_json", artifact.id)
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def ensure_renderable(artifact: Artifact) -> str:
        """Return artifact content, re-validating HTML at read time."""
        if artifact.kind == ArtifactKind.HTML.value:
            try:
                assert_safe_html(artifact.content)
            except ArtifactError:
                logger.error("Stored artifact %s failed the HTML safety check", artifact.id)
                raise
        return artifact.content
