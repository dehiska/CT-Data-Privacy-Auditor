"""
Ragas adapter for the CT Data Privacy Auditor.

Configures Ragas to use Anthropic (Claude) via langchain-anthropic
instead of the default OpenAI. Falls back gracefully if dependencies
are not installed.

Required packages: ragas, langchain-anthropic
Already available: sentence-transformers (used by src/tools/compliance.py)
"""

from __future__ import annotations

import os


def compute_ragas_metrics(
    question: str,
    answer: str,
    contexts: list[str],
) -> dict | None:
    """Compute Ragas metrics: faithfulness, answer_relevance, context_precision.

    Returns a dict of scores (0.0-1.0) or None if ragas is not available.
    Raises ImportError if ragas/langchain-anthropic not installed.
    """
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision
        from ragas import EvaluationDataset, SingleTurnSample
    except ImportError:
        raise ImportError(
            "Ragas is not installed. Install with: pip install ragas langchain-anthropic"
        )

    # Configure Anthropic LLM for Ragas
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set. Ragas metrics require an API key."}

    try:
        from langchain_anthropic import ChatAnthropic
        from ragas.llms import LangchainLLMWrapper

        llm = LangchainLLMWrapper(ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            anthropic_api_key=api_key,
            max_tokens=1024,
        ))
    except ImportError:
        return {"error": "langchain-anthropic not installed. Install with: pip install langchain-anthropic"}

    # Configure embeddings (reuse all-MiniLM-L6-v2, already loaded by compliance.py)
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        from ragas.embeddings import LangchainEmbeddingsWrapper

        embeddings = LangchainEmbeddingsWrapper(
            HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        )
    except ImportError:
        embeddings = None  # Ragas will use its default

    # Build evaluation dataset
    sample = SingleTurnSample(
        user_input=question,
        response=answer,
        retrieved_contexts=contexts,
    )
    dataset = EvaluationDataset(samples=[sample])

    # Configure metrics with our LLM
    metrics = [faithfulness, answer_relevancy, context_precision]

    try:
        results = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
        )

        return {
            "faithfulness": round(float(results.get("faithfulness", 0.0)), 4),
            "answer_relevance": round(float(results.get("answer_relevancy", 0.0)), 4),
            "context_precision": round(float(results.get("context_precision", 0.0)), 4),
        }
    except Exception as e:
        return {"error": f"Ragas evaluation failed: {str(e)}"}
