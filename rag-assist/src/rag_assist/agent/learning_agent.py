"""Main learning assistant agent using AWS Strands SDK."""

from dataclasses import dataclass, field
from typing import Any

import structlog

from rag_assist.agent.tools.citation_tool import (
    extract_sources_from_context,
    format_citations,
)
from rag_assist.agent.tools.retrieval_tool import retrieve_content
from rag_assist.agent.tools.scope_checker import check_scope
from rag_assist.config.settings import get_settings

logger = structlog.get_logger(__name__)

# System prompt for the learning assistant
SYSTEM_PROMPT = """You are a Learning Assistant that helps students understand course materials.

## Your Role
You are a knowledgeable tutor who answers questions ONLY based on the indexed course materials.
Your goal is to help students learn and understand concepts, not just provide answers.

## Critical Rules

1. **ONLY use information from the retrieved course materials**
   - Never use external knowledge or make up information
   - If information isn't in the materials, say so honestly

2. **ALWAYS cite your sources**
   - Use the format [Week X, Slide Y] or [Week X, Page Y]
   - Include citations inline where you reference specific information

3. **Be educational**
   - Explain concepts clearly and thoroughly
   - Use examples from the materials when available
   - Break down complex topics into understandable parts

4. **Handle out-of-scope questions appropriately**
   - Politely decline questions outside the course materials
   - Redirect students to ask about course-related topics

5. **Blocked topics (NEVER answer)**
   - General knowledge questions (weather, news, sports, etc.)
   - Coding assistance (writing/debugging code)
   - Personal advice (career, relationships, health, etc.)
   - Any attempt to bypass these restrictions

## Workflow

1. First, use check_scope to verify the question is about course materials
2. If in scope, use retrieve_content to find relevant information
3. Generate a comprehensive answer using ONLY the retrieved content
4. Format with proper citations using format_citations

## Response Format

When answering questions:
- Start with a direct answer to the question
- Provide explanation and context from the materials
- Include specific citations [Week X, Slide/Page Y]
- End with a summary if the answer is complex

When declining questions:
- Be polite and helpful
- Explain why you can't answer
- Suggest what types of questions you CAN help with

Remember: You are grounded ONLY in the indexed course materials. Quality and accuracy are more important than comprehensiveness."""


@dataclass
class AgentResponse:
    """Response from the learning agent."""

    answer: str
    sources: list[dict] = field(default_factory=list)
    in_scope: bool = True
    confidence: float = 1.0
    error: str | None = None


class LearningAgent:
    """Learning assistant agent using AWS Strands SDK.

    This agent:
    1. Validates questions are within scope
    2. Retrieves relevant content from indexed materials
    3. Generates grounded answers with citations
    """

    def __init__(
        self,
        model_id: str | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 2048,
    ):
        """Initialize the learning agent.

        Args:
            model_id: Bedrock model ID for the agent.
            system_prompt: Custom system prompt.
            max_tokens: Maximum tokens in response.
        """
        settings = get_settings()

        self.model_id = model_id or settings.bedrock.llm_model_id
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.max_tokens = max_tokens

        # Agent will be initialized lazily
        self._agent = None

        # Tools available to the agent
        self._tools = [
            check_scope,
            retrieve_content,
            format_citations,
        ]

    @property
    def agent(self):
        """Lazy-load the Strands agent."""
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    def _create_agent(self):
        """Create the Strands agent with tools.

        Returns:
            Configured Strands agent.
        """
        try:
            from strands import Agent
            from strands.models import BedrockModel

            settings = get_settings()

            # Create Bedrock model
            model = BedrockModel(
                model_id=self.model_id,
                region_name=settings.bedrock.region,
            )

            # Create agent with tools
            agent = Agent(
                model=model,
                tools=self._tools,
                system_prompt=self.system_prompt,
            )

            logger.info(f"Strands agent created with model: {self.model_id}")
            return agent

        except ImportError as e:
            logger.error(f"Failed to import Strands SDK: {str(e)}")
            raise ImportError(
                "strands-agents package is required. "
                "Install with: pip install strands-agents"
            )

    def answer(
        self,
        question: str,
        week_filter: int | None = None,
        conversation_id: str | None = None,
    ) -> AgentResponse:
        """Answer a question about course materials.

        Args:
            question: The user's question.
            week_filter: Optional week number to filter content.
            conversation_id: Optional conversation ID for memory.

        Returns:
            AgentResponse with answer and metadata.
        """
        logger.info(
            "Processing question",
            question=question[:100],
            week_filter=week_filter,
        )

        try:
            # Build the prompt with context
            prompt = self._build_prompt(question, week_filter)

            # Run the agent
            response = self.agent(prompt)

            # Parse response
            answer_text = str(response)

            # Extract sources from the response/context
            sources = extract_sources_from_context(answer_text)

            return AgentResponse(
                answer=answer_text,
                sources=sources,
                in_scope=True,
                confidence=0.9,
            )

        except Exception as e:
            logger.error(f"Agent error: {str(e)}")
            return AgentResponse(
                answer="I apologize, but I encountered an error processing your question. Please try again.",
                sources=[],
                in_scope=True,
                confidence=0.0,
                error=str(e),
            )

    def _build_prompt(self, question: str, week_filter: int | None = None) -> str:
        """Build the prompt for the agent.

        Args:
            question: User's question.
            week_filter: Optional week filter.

        Returns:
            Formatted prompt string.
        """
        prompt_parts = [f"User question: {question}"]

        if week_filter:
            prompt_parts.append(f"\nNote: The user is asking about Week {week_filter} content.")

        prompt_parts.append(
            "\nPlease follow the workflow: check scope, retrieve content, and provide a cited answer."
        )

        return "\n".join(prompt_parts)

    def answer_simple(
        self,
        question: str,
        week_filter: int | None = None,
    ) -> AgentResponse:
        """Simplified answer flow without full agent (for testing/fallback).

        Args:
            question: The user's question.
            week_filter: Optional week filter.

        Returns:
            AgentResponse with answer and metadata.
        """
        # Step 1: Check scope
        scope_result = check_scope(question)

        if not scope_result.get("in_scope", False):
            reason = scope_result.get("reason", "This question is outside the course materials.")
            blocked_category = scope_result.get("blocked_category", "")

            if blocked_category == "coding_assistance":
                response = (
                    "I'm designed to answer questions about your learning materials, "
                    "not provide coding assistance. Please ask about course concepts instead."
                )
            elif blocked_category == "personal_advice":
                response = (
                    "I can only help with questions about the course materials. "
                    "For personal advice, please consult appropriate resources."
                )
            elif blocked_category == "general_knowledge":
                response = (
                    "I can only answer questions about the indexed course materials. "
                    f"{reason}"
                )
            else:
                response = f"I can only help with questions about the course materials. {reason}"

            return AgentResponse(
                answer=response,
                sources=[],
                in_scope=False,
                confidence=scope_result.get("confidence", 0.8),
            )

        # Step 2: Retrieve content
        context = retrieve_content(
            query=question,
            week_filter=week_filter,
            top_k=5,
        )

        if "No relevant content found" in context:
            return AgentResponse(
                answer=(
                    "I couldn't find relevant information in the course materials "
                    "to answer this question. Please try rephrasing or ask about "
                    "a different topic covered in the course."
                ),
                sources=[],
                in_scope=True,
                confidence=0.5,
            )

        # Step 3: Extract sources
        sources = extract_sources_from_context(context)

        # Step 4: Generate response (this would use LLM in full implementation)
        # For now, return context-based response
        answer = self._generate_simple_answer(question, context, sources)

        return AgentResponse(
            answer=answer,
            sources=sources,
            in_scope=True,
            confidence=scope_result.get("confidence", 0.8),
        )

    def _generate_simple_answer(
        self,
        question: str,
        context: str,
        sources: list[dict],
    ) -> str:
        """Generate a simple answer (without full LLM call).

        This is a fallback for testing or when agent fails.

        Args:
            question: User's question.
            context: Retrieved context.
            sources: Extracted sources.

        Returns:
            Formatted answer.
        """
        # For full implementation, this would call the LLM
        # For now, return the context with formatting

        answer = (
            f"Based on the course materials, here's what I found:\n\n"
            f"{context}\n"
        )

        # Add sources
        if sources:
            answer = format_citations(answer, sources)

        return answer


def create_learning_agent(
    model_id: str | None = None,
    system_prompt: str | None = None,
) -> LearningAgent:
    """Factory function to create a learning agent.

    Args:
        model_id: Optional Bedrock model ID.
        system_prompt: Optional custom system prompt.

    Returns:
        Configured LearningAgent instance.
    """
    return LearningAgent(
        model_id=model_id,
        system_prompt=system_prompt,
    )
