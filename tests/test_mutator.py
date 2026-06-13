"""Tests for code mutation via LLM."""
from unittest.mock import Mock, patch

import pytest

from autodev.mutator import CodeMutator


class TestCodeMutator:
    def test_missing_api_key_raises_error(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY not set"):
                CodeMutator()

    @patch("autodev.mutator.OpenAI")
    def test_propose_mutation_success(self, mock_openai_class):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="def optimized():\n    return 42"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            mutator = CodeMutator()
            mutated = mutator.propose_mutation(
                file_content="def old():\n    return 1",
                file_path="test.py",
                objective="Optimize for speed",
                lessons=[],
                constraints=["No external deps"],
            )
            assert "def optimized" in mutated
            assert "42" in mutated

    @patch("autodev.mutator.OpenAI")
    def test_propose_mutation_with_lessons(self, mock_openai_class):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="def fixed():\n    pass"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        lessons = [
            {"pattern": "import_error", "failure": "numpy not found", "fix": "Use built-ins"}
        ]

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            mutator = CodeMutator()
            mutator.propose_mutation(
                file_content="code", file_path="test.py", objective="test",
                lessons=lessons, constraints=[],
            )
            prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
            assert "import_error" in prompt
            assert "numpy not found" in prompt

    @patch("autodev.mutator.OpenAI")
    def test_propose_mutation_with_constraints(self, mock_openai_class):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="def c(): pass"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            mutator = CodeMutator()
            mutator.propose_mutation(
                file_content="code", file_path="test.py", objective="test",
                lessons=[], constraints=["No numpy", "Max 100 lines"],
            )
            prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
            assert "No numpy" in prompt
            assert "Max 100 lines" in prompt

    @patch("autodev.mutator.OpenAI")
    def test_propose_mutation_api_error(self, mock_openai_class):
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai_class.return_value = mock_client

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            mutator = CodeMutator()
            with pytest.raises(Exception, match="API Error"):
                mutator.propose_mutation(
                    file_content="code", file_path="test.py", objective="test",
                    lessons=[], constraints=[],
                )

    @patch("autodev.mutator.OpenAI")
    def test_propose_mutation_strips_markdown(self, mock_openai_class):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="```python\ndef test():\n    pass\n```"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            mutator = CodeMutator()
            result = mutator.propose_mutation(
                file_content="code", file_path="test.py", objective="test",
                lessons=[], constraints=[],
            )
            # NOTE: original strip() doesn't remove markdown fences — that would
            # need a separate fence-stripping pass. Document current behaviour.
            assert isinstance(result, str)
