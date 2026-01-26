"""Orchestrator combining multiple guardrail layers."""

from dataclasses import dataclass
from typing import Any

import structlog

from rag_assist.agent.guardrails.bedrock_guardrails import (
    BedrockGuardrailsClient,
    GuardrailAction,
)
from rag_assist.agent.guardrails.policy_gate import BlockedCategory, PolicyGate

logger = structlog.get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of guardrail validation."""

    passed: bool
    reason: str
    category: str | None = None
    modified_content: str | None = None
    grounding_score: float | None = None


class GuardrailOrchestrator:
    """Orchestrates multiple guardrail layers.

    Layers:
    1. Policy gate - Pattern-based scope enforcement
    2. Bedrock Guardrails - Content filtering and PII detection
    3. Grounding check - Verify responses are based on sources
    """

    def __init__(
        self,
        enable_policy_gate: bool = True,
        enable_bedrock_guardrails: bool = True,
        enable_grounding_check: bool = True,
        grounding_threshold: float = 0.7,
    ):
        """Initialize guardrail orchestrator.

        Args:
            enable_policy_gate: Enable pattern-based policy gate.
            enable_bedrock_guardrails: Enable Bedrock Guardrails.
            enable_grounding_check: Enable grounding verification.
            grounding_threshold: Minimum grounding score.
        """
        self.enable_policy_gate = enable_policy_gate
        self.enable_bedrock_guardrails = enable_bedrock_guardrails
        self.enable_grounding_check = enable_grounding_check
        self.grounding_threshold = grounding_threshold

        self.policy_gate = PolicyGate()
        self.bedrock_guardrails = BedrockGuardrailsClient()

    def validate_input(self, user_input: str) -> ValidationResult:
        """Validate user input before processing.

        Args:
            user_input: User's question or input.

        Returns:
            ValidationResult indicating if input is allowed.
        """
        logger.debug("Validating input", input_length=len(user_input))

        # Layer 1: Policy gate (fast, pattern-based)
        if self.enable_policy_gate:
            policy_result = self.policy_gate.evaluate(user_input)

            if not policy_result.allowed:
                logger.info(
                    "Input blocked by policy gate",
                    category=policy_result.category.value,
                )
                return ValidationResult(
                    passed=False,
                    reason=policy_result.reason,
                    category=policy_result.category.value,
                )

        # Layer 2: Bedrock Guardrails (comprehensive)
        if self.enable_bedrock_guardrails and self.bedrock_guardrails.is_configured:
            guardrail_result = self.bedrock_guardrails.apply(user_input, source="INPUT")

            if guardrail_result.action == GuardrailAction.BLOCKED:
                logger.info(
                    "Input blocked by Bedrock Guardrails",
                    reason=guardrail_result.blocked_reason,
                )
                return ValidationResult(
                    passed=False,
                    reason=guardrail_result.blocked_reason or "Input blocked by content policy",
                    category="bedrock_guardrails",
                )

            # Check if content was modified (e.g., PII anonymized)
            if guardrail_result.action == GuardrailAction.ANONYMIZED:
                return ValidationResult(
                    passed=True,
                    reason="Input passed with modifications",
                    modified_content=guardrail_result.output,
                )

        return ValidationResult(
            passed=True,
            reason="Input passes all guardrail checks",
        )

    def validate_output(
        self,
        response: str,
        sources: list[str] | None = None,
    ) -> ValidationResult:
        """Validate generated output before returning to user.

        Args:
            response: Generated response text.
            sources: Source texts used for generation.

        Returns:
            ValidationResult indicating if output is safe.
        """
        logger.debug("Validating output", response_length=len(response))

        # Layer 1: Bedrock Guardrails output check
        if self.enable_bedrock_guardrails and self.bedrock_guardrails.is_configured:
            guardrail_result = self.bedrock_guardrails.apply(response, source="OUTPUT")

            if guardrail_result.action == GuardrailAction.BLOCKED:
                logger.warning(
                    "Output blocked by Bedrock Guardrails",
                    reason=guardrail_result.blocked_reason,
                )
                return ValidationResult(
                    passed=False,
                    reason="Response blocked by content policy",
                    category="bedrock_guardrails",
                )

        # Layer 2: Grounding check
        if self.enable_grounding_check and sources:
            grounding_result = self.bedrock_guardrails.check_grounding(
                response=response,
                sources=sources,
                grounding_threshold=self.grounding_threshold,
            )

            if not grounding_result.get("grounded", True):
                score = grounding_result.get("score", 0)
                logger.warning(
                    "Output not sufficiently grounded",
                    grounding_score=score,
                )
                return ValidationResult(
                    passed=False,
                    reason="Response not sufficiently grounded in source materials",
                    grounding_score=score,
                )

            return ValidationResult(
                passed=True,
                reason="Output passes all guardrail checks",
                grounding_score=grounding_result.get("score"),
            )

        return ValidationResult(
            passed=True,
            reason="Output passes all guardrail checks",
        )

    def get_refusal_response(self, validation_result: ValidationResult) -> str:
        """Get appropriate refusal response for blocked content.

        Args:
            validation_result: The validation result.

        Returns:
            Polite refusal message.
        """
        if validation_result.category:
            # Try to get category-specific response
            try:
                category = BlockedCategory(validation_result.category)
                return self.policy_gate.get_refusal_response(
                    type("PolicyResult", (), {
                        "category": category,
                        "reason": validation_result.reason,
                    })()
                )
            except ValueError:
                pass

        # Default responses based on reason
        if "grounding" in validation_result.reason.lower():
            return (
                "I apologize, but I couldn't generate a response that's well-supported "
                "by the course materials. Could you try rephrasing your question?"
            )

        if "content policy" in validation_result.reason.lower():
            return (
                "I'm not able to respond to that request. "
                "Is there something about the course materials I can help you with?"
            )

        return (
            "I can only answer questions about the indexed course materials. "
            "What would you like to learn about?"
        )

    def get_status(self) -> dict[str, Any]:
        """Get guardrail system status.

        Returns:
            Status dictionary.
        """
        return {
            "policy_gate_enabled": self.enable_policy_gate,
            "bedrock_guardrails_enabled": self.enable_bedrock_guardrails,
            "bedrock_guardrails_configured": self.bedrock_guardrails.is_configured,
            "grounding_check_enabled": self.enable_grounding_check,
            "grounding_threshold": self.grounding_threshold,
            "guardrail_info": self.bedrock_guardrails.get_guardrail_info(),
        }
