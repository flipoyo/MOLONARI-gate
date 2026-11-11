"""Markdown -> WordPress core blocks (heading, paragraph, list, code, table, image), so any page opens in the editor.

LaTeX `\\( \\)` and `\\[ \\]` pass through for the MathJax-LaTeX plugin. A heading ending in `{#id}` keeps its anchor id
for "Page scroll to id".
"""

from __future__ import annotations

import html
import json
import re

from markdown_it import MarkdownIt

_MATH = re.compile(r"\\\(.+?\\\)|\\\[.+?\\\]", re.S)
_ANCHOR = re.compile(r"\s*\{#([A-Za-z][\w-]*)\}\s*$")
_md = MarkdownIt("commonmark").enable("table")


class RenderError(ValueError):
    pass


def _block(name: str, inner: str, attrs: str = "") -> str:
    return f"<!-- wp:{name}{(' ' + attrs) if attrs else ''} -->\n{inner}\n<!-- /wp:{name} -->"


def _inline(token, env) -> str:
    return _md.renderer.renderInline(token.children or [], _md.options, env).strip()


def _list(tokens, i, env) -> tuple[str, int]:
    ordered = tokens[i].type == "ordered_list_open"
    tag, closing = ("ol", "ordered_list_close") if ordered else ("ul", "bullet_list_close")
    items, i = [], i + 1
    while tokens[i].type != closing:
        if tokens[i].type != "list_item_open":
            raise RenderError(f"unsupported list content: {tokens[i].type}")
        i += 1
        text = []
        while tokens[i].type != "list_item_close":
            if tokens[i].type in ("paragraph_open", "paragraph_close"):
                i += 1
                continue
            if tokens[i].type != "inline":
                raise RenderError("nested lists and blocks inside a list item are not supported")
            text.append(_inline(tokens[i], env))
            i += 1
        items.append(_block("list-item", f"<li>{'<br>'.join(text)}</li>"))
        i += 1
    body = "\n".join(items)
    attrs = '{"ordered":true}' if ordered else ""
    return _block("list", f'<{tag} class="wp-block-list">\n{body}\n</{tag}>', attrs), i + 1


def _table(tokens, i, env) -> tuple[str, int]:
    head, body, section, row = [], [], None, None
    i += 1
    while tokens[i].type != "table_close":
        t = tokens[i]
        if t.type in ("thead_open", "tbody_open"):
            section = "head" if t.type == "thead_open" else "body"
        elif t.type == "tr_open":
            row = []
        elif t.type in ("th_open", "td_open"):
            row.append((t.type[:2], _inline(tokens[i + 1], env)))
        elif t.type == "tr_close":
            (head if section == "head" else body).append(row)
        i += 1
    def rows(rs):
        return "".join("<tr>" + "".join(f"<{tag}>{text}</{tag}>" for tag, text in r) + "</tr>" for r in rs)
    inner = f'<figure class="wp-block-table"><table><thead>{rows(head)}</thead><tbody>{rows(body)}</tbody></table></figure>'
    return _block("table", inner), i + 1


def markdown_to_blocks(text: str) -> str:
    stash: list[str] = []

    def keep(m: re.Match) -> str:
        stash.append(m.group(0))
        return f"MOLOMATH{len(stash) - 1}X"

    env: dict = {}
    tokens = _md.parse(_MATH.sub(keep, text), env)
    out, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        if t.type == "heading_open":
            raw = _inline(tokens[i + 1], env)
            anchor = _ANCHOR.search(raw)
            raw = _ANCHOR.sub("", raw)
            level = int(t.tag[1])
            attrs = {}
            if level != 2:
                attrs["level"] = level
            ident = ""
            if anchor:
                attrs["anchor"] = anchor.group(1)
                ident = f' id="{anchor.group(1)}"'
            out.append(_block("heading", f'<{t.tag} class="wp-block-heading"{ident}>{raw}</{t.tag}>', json.dumps(attrs, separators=(",", ":")) if attrs else ""))
            i += 3
        elif t.type == "paragraph_open":
            inline = tokens[i + 1]
            kids = inline.children or []
            if len(kids) == 1 and kids[0].type == "image":
                src = html.escape(kids[0].attrs["src"], quote=True)
                alt = html.escape(kids[0].content, quote=True)
                out.append(_block("image", f'<figure class="wp-block-image"><img src="{src}" alt="{alt}"/></figure>'))
            else:
                out.append(_block("paragraph", f"<p>{_inline(inline, env)}</p>"))
            i += 3
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            block, i = _list(tokens, i, env)
            out.append(block)
        elif t.type == "fence" or t.type == "code_block":
            out.append(_block("code", f'<pre class="wp-block-code"><code>{html.escape(t.content.rstrip(chr(10)))}</code></pre>'))
            i += 1
        elif t.type == "table_open":
            block, i = _table(tokens, i, env)
            out.append(block)
        else:
            raise RenderError(f"unsupported Markdown element: {t.type}")
    page = "\n\n".join(out) + "\n"
    return re.sub(r"MOLOMATH(\d+)X", lambda m: stash[int(m.group(1))], page)
