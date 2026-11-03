"""Markdown -> HTML for the report, small enough to read in one sitting.

Why not a markdown library? The report comes from our own writer and uses a
known subset: headings, paragraphs, bullets, bold, inline code, fenced code,
tables, rules and ``[n]`` citations. A parser we can audit is safer than a
plugin surface, and it lets citations become buttons instead of text.

Rule: **escape first, format second.** Every character the model produced is
escaped before any tag is added, so a question containing ``<script>`` stays
text even when the heading regex wraps it in ``<h1>``.
"""

from __future__ import annotations

import html
import re

_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_NUMBERED = re.compile(r"^\d+[.)]\s+(.*)$")
_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_URL = re.compile(r"https?://[^\s<]+")
_SEPARATOR = re.compile(r"^:?-{3,}:?$")
_FENCE = "```"


def render_markdown(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()

        if not stripped:
            index += 1
            continue

        if stripped.startswith(_FENCE):
            language = stripped[len(_FENCE) :].strip()
            index += 1
            code: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith(_FENCE):
                code.append(lines[index])
                index += 1
            index += 1  # closing fence
            attrs = f' class="language-{html.escape(language)}"' if language else ""
            blocks.append(
                f"<pre><code{attrs}>{html.escape(chr(10).join(code))}</code></pre>"
            )
            continue

        heading = _HEADING.match(stripped)
        if heading:
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if re.fullmatch(r"-{3,}|\*{3,}", stripped):
            blocks.append("<hr>")
            index += 1
            continue

        if stripped.startswith("|"):
            rows: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index].strip())
                index += 1
            blocks.append(_table(rows))
            continue

        bullet = _BULLET.match(stripped)
        if bullet:
            items: list[str] = []
            while index < len(lines):
                match = _BULLET.match(lines[index].strip())
                if not match:
                    break
                items.append(f"<li>{_inline(match.group(1))}</li>")
                index += 1
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue

        numbered = _NUMBERED.match(stripped)
        if numbered:
            items = []
            while index < len(lines):
                match = _NUMBERED.match(lines[index].strip())
                if not match:
                    break
                items.append(f"<li>{_inline(match.group(1))}</li>")
                index += 1
            blocks.append("<ol>" + "".join(items) + "</ol>")
            continue

        paragraph = [stripped]
        index += 1
        while index < len(lines):
            following = lines[index].strip()
            if (
                not following
                or following.startswith(("#", _FENCE, "|"))
                or _BULLET.match(following)
                or _NUMBERED.match(following)
                or re.fullmatch(r"-{3,}", following)
            ):
                break
            paragraph.append(following)
            index += 1
        blocks.append(f"<p>{_inline(' '.join(paragraph))}</p>")

    return "\n".join(blocks)


# --------------------------------------------------------------------------- #
# inline
# --------------------------------------------------------------------------- #
def _inline(raw: str) -> str:
    """Format one line of text. `raw` is model output, never trusted."""
    text = html.escape(raw, quote=True)

    codes: list[str] = []

    def stash(match: re.Match[str]) -> str:
        codes.append(f"<code>{match.group(1)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = _CODE.sub(stash, text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _CITE.sub(_citation, text)
    text = _URL.sub(_link, text)

    for number, code in enumerate(codes):
        text = text.replace(f"\x00{number}\x00", code)
    return text


def _citation(match: re.Match[str]) -> str:
    numbers = [part.strip() for part in match.group(1).split(",") if part.strip()]
    if not numbers:
        return match.group(0)
    refs = ",".join(numbers)
    label = ", ".join(numbers)
    return (
        f'<button type="button" class="cite" data-refs="{refs}" '
        f'title="Show source {label}">[{label}]</button>'
    )


def _link(match: re.Match[str]) -> str:
    url = match.group(0)
    trailing = ""
    while url and url[-1] in ".,;:":
        trailing = url[-1] + trailing
        url = url[:-1]
    return (
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
        f"{trailing}"
    )


# --------------------------------------------------------------------------- #
# tables (the evidence appendix)
# --------------------------------------------------------------------------- #
def _cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR.match(cell) for cell in cells)


def _table(rows: list[str]) -> str:
    parsed = [_cells(row) for row in rows]
    header: list[str] = []
    if len(parsed) >= 2 and _is_separator(parsed[1]):
        header = parsed[0]
        parsed = parsed[2:]
    else:
        parsed = [row for row in parsed if not _is_separator(row)]

    parts = ['<div class="table-wrap"><table>']
    if header:
        parts.append(
            "<thead><tr>"
            + "".join(f"<th>{_inline(cell)}</th>" for cell in header)
            + "</tr></thead>"
        )
    parts.append("<tbody>")
    for row in parsed:
        parts.append(
            "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>"
        )
    parts.append("</tbody></table></div>")
    return "".join(parts)
