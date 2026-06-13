"""Code mutation via LLM with lesson-aware prompting."""
import os

from openai import OpenAI


class CodeMutator:
    """Proposes code mutations using an LLM, informed by past lessons."""

    def __init__(self, model: str = "gpt-4o"):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Export it to enable autonomous mutations."
            )
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def propose_mutation(
        self, file_content: str, file_path: str, objective: str,
        lessons: list[dict], constraints: list[str],
    ) -> str:
        """Ask LLM to propose an improvement."""
        lessons_text = ""
        if lessons:
            lessons_text = "\n## Past Failures (AVOID THESE)\n"
            for lesson in lessons[:5]:
                lessons_text += f"- Pattern: {lesson['pattern']}\n"
                lessons_text += f"  Failure: {lesson['failure']}\n"
                if lesson.get("fix"):
                    lessons_text += f"  Fix: {lesson['fix']}\n"

        prompt = f"""You are an autonomous code optimizer.

## Objective
{objective}

## Constraints
{chr(10).join(f'- {c}' for c in constraints)}

## Current File: {file_path}
```python
{file_content}
```

{lessons_text}

## Task
Propose ONE specific, testable mutation to improve the file.
Return ONLY the complete, modified file content. No explanations. No markdown fences.
"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        content = response.choices[0].message.content
        return (content or "").strip()
