"""Code mutation via LLM with lesson-aware prompting."""
import os

from openai import OpenAI


class CodeMutator:
    """Proposes code mutations using an LLM, informed by past lessons.

    Profile-aware: callers (e.g. SwarmCoordinator) can override the
    model name and temperature per agent. Default tuned for SIN-Code
    precise/fast profile (gpt-4o, low temperature).
    """

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.7):
        # Lazy OPENAI_API_KEY check — only required at propose_mutation()
        # time so unit tests that never call it don't need a key.
        self._api_key = os.environ.get("OPENAI_API_KEY")
        if temperature < 0 or temperature > 2:
            raise ValueError(f"temperature must be in [0, 2], got {temperature}")
        self.model = model
        self.temperature = temperature

    def propose_mutation(
        self, file_content: str, file_path: str, objective: str,
        lessons: list[dict], constraints: list[str],
    ) -> str:
        """Ask LLM to propose an improvement."""
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Export it to enable autonomous mutations."
            )
        # Lazy client: don't pay connection cost until we actually call.
        if not hasattr(self, "_client"):
            self._client = OpenAI(api_key=self._api_key)
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
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )

        content = response.choices[0].message.content
        return (content or "").strip()
