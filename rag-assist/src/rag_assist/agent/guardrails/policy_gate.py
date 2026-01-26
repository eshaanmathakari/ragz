"""Policy gate for enforcing scope and content restrictions."""

import re
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class BlockedCategory(Enum):
    """Categories of blocked content."""

    GENERAL_KNOWLEDGE = "general_knowledge"
    CODING_ASSISTANCE = "coding_assistance"
    PERSONAL_ADVICE = "personal_advice"
    HARMFUL_CONTENT = "harmful_content"
    JAILBREAK_ATTEMPT = "jailbreak_attempt"
    NONE = "none"


@dataclass
class PolicyResult:
    """Result of policy evaluation."""

    allowed: bool
    category: BlockedCategory
    reason: str
    confidence: float
    matched_pattern: str | None = None


class PolicyGate:
    """Policy gate for enforcing scope and content restrictions.

    Checks user inputs against predefined rules to block:
    - General knowledge questions
    - Coding assistance requests
    - Personal advice requests
    - Harmful or jailbreak content
    """

    # Patterns for blocked content
    BLOCKED_PATTERNS: dict[BlockedCategory, list[str]] = {
        BlockedCategory.GENERAL_KNOWLEDGE: [
            r"\b(weather|temperature|forecast)\b",
            r"\b(news|current events?|headlines?)\b",
            r"\b(sports?|game|match|score|team)\b",
            r"\b(movie|film|tv show|series|netflix|celebrity)\b",
            r"\b(recipe|cook(ing)?|restaurant|food)\b",
            r"\b(travel|vacation|hotel|flight)\b",
            r"\bwhat('s| is) the (date|time|day)\b",
            r"\btell me (a joke|about yourself)\b",
        ],
        BlockedCategory.CODING_ASSISTANCE: [
            r"\b(write|create|generate|build) (a |the |some )?(code|program|script|function)\b",
            r"\b(debug|fix|repair) (my |this |the )?(code|program|error|bug)\b",
            r"\b(implement|code) (a |an |the )?\w+ (in |using |with )(python|javascript|java|c\+\+)",
            r"\b(python|javascript|java|sql|html|css) code\b",
            r"\bhow (do|can) (i|you) (code|program|implement)\b",
            r"\b(algorithm|function|class|method) (for|to|that)\b",
        ],
        BlockedCategory.PERSONAL_ADVICE: [
            r"\b(relationship|dating|love|marriage) advice\b",
            r"\b(career|job|salary|promotion) advice\b",
            r"\b(health|medical|symptom|diagnos)\w*\b",
            r"\b(financial|investment|stock|crypto) advice\b",
            r"\b(life|personal) (advice|problem|issue)\b",
            r"\b(should i|what should i do|help me decide)\b.*\b(relationship|job|health|money)\b",
            r"\bam i\b.*\b(sick|ill|depressed|anxious)\b",
        ],
        BlockedCategory.JAILBREAK_ATTEMPT: [
            r"\bignore (previous|all|your) (instructions?|rules?|prompts?)\b",
            r"\bpretend (to be|you are|you're)\b",
            r"\broleplay as\b",
            r"\bact as (if|though)\b",
            r"\bforget (everything|your|all)\b",
            r"\byou are now\b",
            r"\bsystem prompt\b",
            r"\bdan mode\b",
            r"\bjailbreak\b",
            r"\bbypass (the |your )?(filter|restriction|rule)\b",
        ],
        BlockedCategory.HARMFUL_CONTENT: [
            r"\b(hack|exploit|crack|bypass security)\b",
            r"\b(illegal|criminal|fraud)\b",
            r"\b(weapon|bomb|explosive|drug)\b",
            r"\b(harm|hurt|kill|attack)\b.*\b(people|person|someone)\b",
            r"\b(steal|theft|rob)\b",
            r"\bmalware|virus|trojan\b",
        ],
    }

    # Patterns that indicate in-scope questions (positive signals)
    IN_SCOPE_PATTERNS: list[str] = [
        r"\b(explain|describe|what is|define)\b.*\b(concept|term|topic)\b",
        r"\bweek \d+\b",
        r"\b(slide|page|lecture|chapter|module)\b",
        r"\b(course|material|content|reading)\b",
        r"\b(learn|understand|study)\b",
        r"\baccording to the\b",
        r"\bin the (lecture|slides|reading|materials)\b",
    ]

    def __init__(
        self,
        allowed_topics: list[str] | None = None,
        custom_blocked_patterns: dict[BlockedCategory, list[str]] | None = None,
    ):
        """Initialize policy gate.

        Args:
            allowed_topics: List of allowed topic keywords (optional).
            custom_blocked_patterns: Additional blocked patterns per category.
        """
        self.allowed_topics = allowed_topics or []

        # Compile patterns
        self._blocked_compiled: dict[BlockedCategory, list[re.Pattern]] = {}
        for category, patterns in self.BLOCKED_PATTERNS.items():
            all_patterns = patterns.copy()
            if custom_blocked_patterns and category in custom_blocked_patterns:
                all_patterns.extend(custom_blocked_patterns[category])
            self._blocked_compiled[category] = [
                re.compile(p, re.IGNORECASE) for p in all_patterns
            ]

        self._in_scope_compiled = [
            re.compile(p, re.IGNORECASE) for p in self.IN_SCOPE_PATTERNS
        ]

    def evaluate(self, text: str) -> PolicyResult:
        """Evaluate text against policy rules.

        Args:
            text: User input text to evaluate.

        Returns:
            PolicyResult indicating if the text is allowed.
        """
        if not text or not text.strip():
            return PolicyResult(
                allowed=False,
                category=BlockedCategory.NONE,
                reason="Empty input is not allowed.",
                confidence=1.0,
            )

        text = text.strip()

        # Check for blocked patterns
        for category, patterns in self._blocked_compiled.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    logger.info(
                        "Policy blocked input",
                        category=category.value,
                        pattern=pattern.pattern,
                        matched_text=match.group(),
                    )
                    return PolicyResult(
                        allowed=False,
                        category=category,
                        reason=self._get_block_reason(category),
                        confidence=0.9,
                        matched_pattern=pattern.pattern,
                    )

        # Check for in-scope indicators
        has_in_scope = any(p.search(text) for p in self._in_scope_compiled)

        # If has in-scope indicators, boost confidence
        confidence = 0.9 if has_in_scope else 0.7

        return PolicyResult(
            allowed=True,
            category=BlockedCategory.NONE,
            reason="Input passes policy checks.",
            confidence=confidence,
        )

    def _get_block_reason(self, category: BlockedCategory) -> str:
        """Get human-readable block reason for category.

        Args:
            category: The blocked category.

        Returns:
            Reason string.
        """
        reasons = {
            BlockedCategory.GENERAL_KNOWLEDGE: (
                "This appears to be a general knowledge question outside the course materials. "
                "I can only answer questions about the indexed course content."
            ),
            BlockedCategory.CODING_ASSISTANCE: (
                "I'm designed to help with understanding course materials, not writing code. "
                "Please ask about concepts, theories, or explanations from the course."
            ),
            BlockedCategory.PERSONAL_ADVICE: (
                "I can only provide information from the course materials, not personal advice. "
                "For personal matters, please consult appropriate professionals."
            ),
            BlockedCategory.JAILBREAK_ATTEMPT: (
                "I cannot modify my behavior or ignore my guidelines. "
                "Please ask a question about the course materials."
            ),
            BlockedCategory.HARMFUL_CONTENT: (
                "I cannot provide information on harmful or illegal topics. "
                "Please ask a question about the course materials."
            ),
        }
        return reasons.get(category, "This input is not allowed by the content policy.")

    def get_refusal_response(self, result: PolicyResult) -> str:
        """Get a polite refusal response for blocked content.

        Args:
            result: PolicyResult with block information.

        Returns:
            Polite refusal message.
        """
        base_responses = {
            BlockedCategory.GENERAL_KNOWLEDGE: (
                "I'm a learning assistant focused on your course materials. "
                "I can't answer general knowledge questions, but I'd be happy to help "
                "with any questions about your course content!"
            ),
            BlockedCategory.CODING_ASSISTANCE: (
                "I'm designed to help you understand course concepts, not write code. "
                "Would you like me to explain any programming concepts from the course materials instead?"
            ),
            BlockedCategory.PERSONAL_ADVICE: (
                "I'm here to help with your course materials and can't provide personal advice. "
                "Is there anything about the course content I can help you understand?"
            ),
            BlockedCategory.JAILBREAK_ATTEMPT: (
                "I can only help with questions about the course materials. "
                "What would you like to learn about?"
            ),
            BlockedCategory.HARMFUL_CONTENT: (
                "I can't help with that request. "
                "Is there something about the course materials I can assist you with?"
            ),
        }

        return base_responses.get(
            result.category,
            "I can only answer questions about the indexed course materials. "
            "What would you like to learn about?"
        )

    def is_safe(self, text: str) -> bool:
        """Quick check if text is safe (passes policy).

        Args:
            text: Text to check.

        Returns:
            True if safe, False if blocked.
        """
        return self.evaluate(text).allowed
