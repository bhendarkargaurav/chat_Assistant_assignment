from backend.app.agent.intents import Intent
from backend.app.exceptions import ConfigurationError
from backend.app.skills.artifacts import HtmlArtifactSkill, MarkdownArtifactSkill
from backend.app.skills.base import Skill
from backend.app.skills.qa import GroundedQASkill
from backend.app.skills.ship30 import Ship30Skill

SKILL_REGISTRY: dict[Intent, Skill] = {
    Intent.QA: GroundedQASkill(),
    Intent.SHIP30_ESSAY: Ship30Skill(),
    Intent.ARTIFACT_MARKDOWN: MarkdownArtifactSkill(),
    Intent.ARTIFACT_HTML: HtmlArtifactSkill(),
}


def get_skill(intent: Intent) -> Skill:
    skill = SKILL_REGISTRY.get(intent)
    if skill is None:
        raise ConfigurationError(f"No skill registered for intent {intent}")
    return skill


def describe_skills() -> list[dict]:
    return [
        {
            "intent": intent.value,
            "skill": skill.name,
            "description": skill.description,
        }
        for intent, skill in SKILL_REGISTRY.items()
    ]
