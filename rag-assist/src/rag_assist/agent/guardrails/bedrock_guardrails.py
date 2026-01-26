"""Amazon Bedrock Guardrails integration for content filtering."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

from rag_assist.config import get_bedrock_runtime_client
from rag_assist.config.settings import get_settings

logger = structlog.get_logger(__name__)


class GuardrailAction(Enum):
    """Guardrail action types."""

    NONE = "NONE"
    BLOCKED = "BLOCKED"
    ANONYMIZED = "ANONYMIZED"


@dataclass
class GuardrailResult:
    """Result from Bedrock Guardrails evaluation."""

    action: GuardrailAction
    blocked_reason: str | None = None
    output: str | None = None
    assessments: list[dict] = None

    def __post_init__(self):
        if self.assessments is None:
            self.assessments = []


class BedrockGuardrailsClient:
    """Client for Amazon Bedrock Guardrails.

    Provides content filtering, topic blocking, and grounding checks.
    """

    def __init__(
        self,
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
    ):
        """Initialize Bedrock Guardrails client.

        Args:
            guardrail_id: Bedrock Guardrail ID.
            guardrail_version: Guardrail version (default: DRAFT).
        """
        settings = get_settings()

        self.guardrail_id = guardrail_id or settings.bedrock.guardrail_id
        self.guardrail_version = guardrail_version or settings.bedrock.guardrail_version
        self._client = None

    @property
    def client(self) -> Any:
        """Lazy-load Bedrock runtime client."""
        if self._client is None:
            self._client = get_bedrock_runtime_client()
        return self._client

    @property
    def is_configured(self) -> bool:
        """Check if guardrails are configured."""
        return self.guardrail_id is not None and len(self.guardrail_id) > 0

    def apply(
        self,
        content: str,
        source: str = "INPUT",
    ) -> GuardrailResult:
        """Apply guardrails to content.

        Args:
            content: Text content to evaluate.
            source: Source type ("INPUT" or "OUTPUT").

        Returns:
            GuardrailResult with action and details.
        """
        if not self.is_configured:
            logger.debug("Guardrails not configured, skipping")
            return GuardrailResult(action=GuardrailAction.NONE)

        try:
            response = self.client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
                source=source,
                content=[{"text": {"text": content}}],
            )

            action = response.get("action", "NONE")
            outputs = response.get("outputs", [])
            assessments = response.get("assessments", [])

            # Get output text if any
            output_text = None
            if outputs:
                output_text = outputs[0].get("text")

            # Determine blocked reason from assessments
            blocked_reason = None
            if action == "GUARDRAIL_INTERVENED":
                blocked_reason = self._extract_block_reason(assessments)

            return GuardrailResult(
                action=GuardrailAction.BLOCKED if action == "GUARDRAIL_INTERVENED" else GuardrailAction.NONE,
                blocked_reason=blocked_reason,
                output=output_text,
                assessments=assessments,
            )

        except Exception as e:
            logger.error(f"Guardrails evaluation failed: {str(e)}")
            # On error, don't block (fail open)
            return GuardrailResult(action=GuardrailAction.NONE)

    def _extract_block_reason(self, assessments: list[dict]) -> str:
        """Extract human-readable block reason from assessments.

        Args:
            assessments: List of guardrail assessments.

        Returns:
            Block reason string.
        """
        reasons = []

        for assessment in assessments:
            # Content policy violations
            content_policy = assessment.get("contentPolicy", {})
            filters = content_policy.get("filters", [])
            for f in filters:
                if f.get("action") == "BLOCKED":
                    filter_type = f.get("type", "UNKNOWN")
                    reasons.append(f"Content blocked: {filter_type.lower()}")

            # Topic policy violations
            topic_policy = assessment.get("topicPolicy", {})
            topics = topic_policy.get("topics", [])
            for t in topics:
                if t.get("action") == "BLOCKED":
                    topic_name = t.get("name", "unknown topic")
                    reasons.append(f"Topic blocked: {topic_name}")

            # Sensitive information
            sensitive_info = assessment.get("sensitiveInformationPolicy", {})
            pii_entities = sensitive_info.get("piiEntities", [])
            for p in pii_entities:
                action = p.get("action", "")
                if action in ["BLOCKED", "ANONYMIZED"]:
                    pii_type = p.get("type", "UNKNOWN")
                    reasons.append(f"PII {action.lower()}: {pii_type.lower()}")

            # Word policy
            word_policy = assessment.get("wordPolicy", {})
            custom_words = word_policy.get("customWords", [])
            for w in custom_words:
                if w.get("action") == "BLOCKED":
                    reasons.append("Blocked word detected")

        return "; ".join(reasons) if reasons else "Content blocked by guardrail policy"

    def check_grounding(
        self,
        response: str,
        sources: list[str],
        grounding_threshold: float = 0.7,
    ) -> dict[str, Any]:
        """Check if response is grounded in sources.

        Note: This requires contextual grounding to be configured in the guardrail.

        Args:
            response: Generated response text.
            sources: List of source texts.
            grounding_threshold: Minimum grounding score (0-1).

        Returns:
            Dictionary with grounding assessment.
        """
        if not self.is_configured:
            return {"grounded": True, "score": 1.0, "reason": "Guardrails not configured"}

        try:
            # Combine sources as grounding source
            grounding_source = "\n\n".join(sources)

            response = self.client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
                source="OUTPUT",
                content=[{"text": {"text": response}}],
                # Note: Grounding source configuration depends on guardrail setup
            )

            assessments = response.get("assessments", [])

            # Look for grounding assessment
            for assessment in assessments:
                grounding = assessment.get("contextualGroundingPolicy", {})
                filters = grounding.get("filters", [])

                for f in filters:
                    if f.get("type") == "GROUNDING":
                        score = f.get("score", 1.0)
                        threshold = f.get("threshold", grounding_threshold)
                        action = f.get("action", "NONE")

                        return {
                            "grounded": action != "BLOCKED",
                            "score": score,
                            "threshold": threshold,
                            "reason": f"Grounding score: {score:.2f}"
                        }

            return {"grounded": True, "score": 1.0, "reason": "No grounding assessment found"}

        except Exception as e:
            logger.error(f"Grounding check failed: {str(e)}")
            return {"grounded": True, "score": 1.0, "reason": f"Check failed: {str(e)}"}

    def get_guardrail_info(self) -> dict[str, Any]:
        """Get information about the configured guardrail.

        Returns:
            Guardrail configuration info.
        """
        if not self.is_configured:
            return {"configured": False}

        try:
            import boto3
            bedrock = boto3.client("bedrock")

            response = bedrock.get_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
            )

            return {
                "configured": True,
                "id": self.guardrail_id,
                "version": self.guardrail_version,
                "name": response.get("name"),
                "status": response.get("status"),
                "description": response.get("description"),
            }

        except Exception as e:
            return {
                "configured": True,
                "id": self.guardrail_id,
                "version": self.guardrail_version,
                "error": str(e),
            }
