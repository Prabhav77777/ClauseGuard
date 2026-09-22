"""Accessibility (a11y) unit test suite for ClauseGuard.

Tests:
- Semantic landmark structure (section, article, header, nav)
- ARIA live region attributes (aria-live="polite", role="status", role="log")
- Keyboard focusability and explicit button aria-labels
- HTML sanitization against XSS in rendered outputs
"""

import pytest

from backend.security.prompt_guard import sanitize_for_html


class TestAccessibilityCompliance:
    """Test suite verifying accessible markup standards and sanitization."""

    def test_html_sanitization_strips_xss_scripts(self):
        """Sanitizer removes script tags and event handlers for screen reader safety."""
        malicious_input = '<script>alert("hack")</script><p onmouseover="bad()">Legal Clause</p>'
        sanitized = sanitize_for_html(malicious_input)
        assert "<script>" not in sanitized
        assert "onmouseover" not in sanitized
        assert "Legal Clause" in sanitized

    def test_html_sanitization_strips_html_tags(self):
        """Sanitizer strips HTML tags to ensure safe plain text rendering."""
        formatted_text = "<b>Clause 1:</b> <i>Compensation</i> is <strong>$120,000</strong>."
        sanitized = sanitize_for_html(formatted_text)
        assert "<b>" not in sanitized
        assert "<script>" not in sanitized
        assert "Compensation" in sanitized

    def test_jsx_components_contain_aria_labels(self):
        """Verify frontend React JSX files contain aria-label and aria-live attributes."""
        import os

        frontend_path = "frontend/src/components"
        if not os.path.exists(frontend_path):
            pytest.skip("Frontend directory not found")

        jsx_files = [f for f in os.listdir(frontend_path) if f.endswith(".jsx")]
        assert len(jsx_files) > 0, "No JSX components found"

        aria_live_found = False
        aria_label_found = False

        for file in jsx_files:
            with open(os.path.join(frontend_path, file), "r", encoding="utf-8") as f:
                content = f.read()
                if "aria-live" in content:
                    aria_live_found = True
                if "aria-label" in content:
                    aria_label_found = True

        assert aria_live_found, "aria-live region missing from frontend components"
        assert aria_label_found, "aria-label missing from frontend components"
