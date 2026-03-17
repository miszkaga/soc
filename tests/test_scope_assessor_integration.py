"""
Integration tests for scope_assessor.py

Covers:
- File selection at runtime (prefers sanitized, falls back to original)
- LLM receives anonymised text, not raw sensitive names (OpenAI mocked)
- load_system_description raises FileNotFoundError for missing path
- Result JSON contains the expected keys
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scope_assessor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SANITIZED_TEXT = (
    "[ORGANIZATION_1] provides a HIPAA-compliant platform.\n"
    "V. SUBSERVICE ORGANIZATIONS (CARVE-OUT METHOD)\n"
    "1. [ORGANIZATION_2]:\n"
    "   - Service: Cloud infrastructure.\n"
    "2. [ORGANIZATION_3]:\n"
    "   - Service: CRM.\n"
)

RAW_TEXT = (
    "MedCore Health Inc. provides a HIPAA-compliant platform.\n"
    "V. SUBSERVICE ORGANIZATIONS (CARVE-OUT METHOD)\n"
    "1. Microsoft Azure:\n"
    "   - Service: Cloud infrastructure.\n"
    "2. Salesforce:\n"
    "   - Service: CRM.\n"
)

_VENDOR_RESPONSE = json.dumps({
    "subservice_organizations": [
        {"vendor_name": "[ORGANIZATION_2]", "service_provided": "Cloud infrastructure",
         "reliance_phrases": ["Cloud infrastructure"]},
        {"vendor_name": "[ORGANIZATION_3]", "service_provided": "CRM",
         "reliance_phrases": ["CRM"]},
    ]
})

_CLASSIFICATION_RESPONSE = json.dumps({
    "classification": "CARVE_OUT",
    "confidence": 0.95,
    "reasoning": "Text explicitly describes carve-out method.",
    "evidence": ["CARVE-OUT METHOD"],
})

_CONTROLS_RESPONSE = json.dumps({
    "required_controls": [
        {"control_id": "CC6.1", "requirement": "Review SOC 2 reports", "rationale": "Carve-out"},
    ]
})

_OSCAL_RESPONSE = json.dumps({
    "leveraged_authorizations": [],
    "remarks": "Carve-out.",
})


def _make_mock_completion(content: str) -> MagicMock:
    """Build a minimal mock that mimics openai.ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def _make_side_effect():
    """
    Factory that returns a fresh side-effect callable.

    Each successive call to scope_assessor.main() makes 4 API requests
    (identify vendors → classify → controls → OSCAL hint).  By creating
    a new callable per test we avoid accumulated state from previous tests.
    """
    responses = [
        _VENDOR_RESPONSE,
        _CLASSIFICATION_RESPONSE,
        _CONTROLS_RESPONSE,
        _OSCAL_RESPONSE,
    ]
    state = {"count": 0}

    def side_effect(*args, **kwargs):
        idx = min(state["count"], len(responses) - 1)
        state["count"] += 1
        return _make_mock_completion(responses[idx])

    return side_effect


# ---------------------------------------------------------------------------
# load_system_description unit tests
# ---------------------------------------------------------------------------

class TestLoadSystemDescription:
    def test_loads_existing_file(self, tmp_path):
        p = tmp_path / "desc.txt"
        p.write_text("Hello, world.", encoding="utf-8")
        result = scope_assessor.load_system_description(str(p))
        assert result == "Hello, world."

    def test_raises_for_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            scope_assessor.load_system_description(str(tmp_path / "missing.txt"))


# ---------------------------------------------------------------------------
# File selection: sanitized preferred over original
# ---------------------------------------------------------------------------

class TestFileSelectionAtRuntime:
    """
    scope_assessor.main() resolves the input file at call time.
    When the sanitized file is present it should be used; otherwise fall back.
    """

    def _patch_and_run(self, tmp_path, *, sanitized_exists: bool, monkeypatch):
        sanitized = tmp_path / "sanitized_system_description.txt"
        original = tmp_path / "system_description.txt"
        original.write_text(RAW_TEXT, encoding="utf-8")

        if sanitized_exists:
            sanitized.write_text(SANITIZED_TEXT, encoding="utf-8")

        monkeypatch.setattr(scope_assessor, "_SANITIZED_FILE", str(sanitized))
        monkeypatch.setattr(scope_assessor, "_ORIGINAL_FILE", str(original))
        monkeypatch.setattr(scope_assessor, "OUTPUT_FILE", str(tmp_path / "scope_strategy.json"))

        captured_texts = []
        # Create a fresh side-effect per run so successive calls within one
        # test return the correct response (vendor → classification → controls → OSCAL).
        se = _make_side_effect()

        def fake_create(**kwargs):
            messages = kwargs.get("messages", [])
            for m in messages:
                if "content" in m:
                    captured_texts.append(m["content"])
            return se(**kwargs)

        with patch.object(scope_assessor.client.chat.completions, "create",
                          side_effect=fake_create):
            scope_assessor.main()

        return captured_texts, sanitized_exists

    def test_uses_sanitized_file_when_present(self, tmp_path, monkeypatch):
        texts, _ = self._patch_and_run(tmp_path, sanitized_exists=True, monkeypatch=monkeypatch)
        combined = "\n".join(texts)
        # Sanitized tokens should appear
        assert "[ORGANIZATION_" in combined
        # Real names must NOT appear in anything sent to the LLM
        assert "MedCore Health Inc." not in combined
        assert "Microsoft Azure" not in combined
        assert "Salesforce" not in combined

    def test_falls_back_to_original_when_sanitized_missing(self, tmp_path, monkeypatch):
        texts, _ = self._patch_and_run(tmp_path, sanitized_exists=False, monkeypatch=monkeypatch)
        combined = "\n".join(texts)
        # Original names will be present (fallback path — warns user)
        assert "MedCore Health Inc." in combined or "Microsoft Azure" in combined

    def test_output_json_written(self, tmp_path, monkeypatch):
        self._patch_and_run(tmp_path, sanitized_exists=True, monkeypatch=monkeypatch)
        output = tmp_path / "scope_strategy.json"
        assert output.exists(), "scope_strategy.json must be written"
        data = json.loads(output.read_text())
        assert "subservice_organizations" in data
        assert "reporting_method" in data

    def test_output_json_records_sanitized_file_path(self, tmp_path, monkeypatch):
        """The scope strategy must record which file was actually read."""
        texts, _ = self._patch_and_run(tmp_path, sanitized_exists=True, monkeypatch=monkeypatch)
        output = tmp_path / "scope_strategy.json"
        data = json.loads(output.read_text())
        assert "sanitized" in data.get("system_description_file", "")


# ---------------------------------------------------------------------------
# LLM receives anonymised text (privacy guarantee)
# ---------------------------------------------------------------------------

class TestLLMReceivesAnonymisedText:
    """
    After Phase 0 sanitization the scope assessor must never send the
    original sensitive names to the OpenAI API.
    """

    def test_no_real_names_in_llm_prompts(self, tmp_path, monkeypatch):
        sanitized = tmp_path / "sanitized_system_description.txt"
        sanitized.write_text(SANITIZED_TEXT, encoding="utf-8")

        monkeypatch.setattr(scope_assessor, "_SANITIZED_FILE", str(sanitized))
        monkeypatch.setattr(scope_assessor, "_ORIGINAL_FILE", str(tmp_path / "orig.txt"))
        monkeypatch.setattr(scope_assessor, "OUTPUT_FILE", str(tmp_path / "out.json"))

        llm_inputs = []

        se = _make_side_effect()

        def capture_create(**kwargs):
            for msg in kwargs.get("messages", []):
                llm_inputs.append(msg.get("content", ""))
            return se(**kwargs)

        with patch.object(scope_assessor.client.chat.completions, "create",
                          side_effect=capture_create):
            scope_assessor.main()

        combined = "\n".join(llm_inputs)
        sensitive_names = [
            "MedCore Health Inc.", "Microsoft Azure", "Salesforce",
            "Datadog", "Zendesk", "GitLab", "Dallas",
        ]
        for name in sensitive_names:
            assert name not in combined, (
                f"Real name '{name}' leaked into LLM prompt — privacy violation"
            )

    def test_tokens_present_in_llm_prompts(self, tmp_path, monkeypatch):
        """Anonymisation tokens like [ORGANIZATION_1] should be visible in prompts."""
        sanitized = tmp_path / "sanitized_system_description.txt"
        sanitized.write_text(SANITIZED_TEXT, encoding="utf-8")

        monkeypatch.setattr(scope_assessor, "_SANITIZED_FILE", str(sanitized))
        monkeypatch.setattr(scope_assessor, "_ORIGINAL_FILE", str(tmp_path / "orig.txt"))
        monkeypatch.setattr(scope_assessor, "OUTPUT_FILE", str(tmp_path / "out.json"))

        llm_inputs = []
        se = _make_side_effect()

        def capture_create(**kwargs):
            for msg in kwargs.get("messages", []):
                llm_inputs.append(msg.get("content", ""))
            return se(**kwargs)

        with patch.object(scope_assessor.client.chat.completions, "create",
                          side_effect=capture_create):
            scope_assessor.main()

        combined = "\n".join(llm_inputs)
        assert "[ORGANIZATION_" in combined, (
            "LLM prompts should contain anonymisation tokens, not real names"
        )
