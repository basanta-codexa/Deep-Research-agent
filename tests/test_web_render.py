from __future__ import annotations

from web.render import render_markdown


def test_model_text_is_escaped_before_any_tag_is_added():
    html = render_markdown("# <script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_citations_become_buttons():
    html = render_markdown("Threads [1] and [1, 2] race.")
    assert 'class="cite"' in html
    assert 'data-refs="1"' in html
    assert 'data-refs="1,2"' in html
    assert "[1, 2]" in html


def test_citation_inside_bold_still_works():
    html = render_markdown("**Important [3]**")
    assert "<strong>" in html
    assert 'data-refs="3"' in html


def test_paragraphs_headings_and_rules():
    html = render_markdown("# Title\n\nA line\nwrapped.\n\n---\n\n## Section")
    assert "<h1>Title</h1>" in html
    assert "<p>A line wrapped.</p>" in html
    assert "<hr>" in html
    assert "<h2>Section</h2>" in html


def test_bullets_and_numbered_lists():
    html = render_markdown("- one\n- two\n\n1. first\n2. second")
    assert "<ul><li>one</li><li>two</li></ul>" in html
    assert "<ol><li>first</li><li>second</li></ol>" in html


def test_inline_code_is_not_formatted_as_markdown():
    html = render_markdown("Use `**not bold**` here.")
    assert "<code>**not bold**</code>" in html
    assert "<strong>" not in html


def test_fenced_code_is_escaped_and_keeps_lines():
    html = render_markdown("```python\nprint('<hi>')\n```")
    assert '<code class="language-python">' in html
    assert "print(" in html
    assert "&lt;hi&gt;" in html
    assert "<hi>" not in html


def test_links_are_external_and_safe():
    html = render_markdown("See https://example.com/a?b=1&c=2.")
    assert 'href="https://example.com/a?b=1&amp;c=2"' in html
    assert 'rel="noopener noreferrer"' in html
    assert "</a>." in html


def test_evidence_appendix_table():
    markdown = "\n".join(
        [
            "| ref | claim | quote | span |",
            "| --- | --- | --- | --- |",
            "| [1] | GIL blocks threads | \"bytecodes\" | 12-34 |",
        ]
    )
    html = render_markdown(markdown)
    assert "<thead>" in html
    assert "<th>ref</th>" in html
    # The appendix ref is clickable too: it opens the same source drawer.
    assert 'data-refs="1"' in html
    assert "<td>GIL blocks threads</td>" in html
    assert "<td>12-34</td>" in html


def test_empty_markdown():
    assert render_markdown("") == ""


def test_escapes_inside_table_cells():
    html = render_markdown("| a | b |\n| --- | --- |\n| <img> | x |")
    assert "<img>" not in html
    assert "&lt;img&gt;" in html
