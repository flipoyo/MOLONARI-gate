import re

import pytest

from molosite.render import RenderError, markdown_to_blocks

DOC = """## Title {#top}

A paragraph with `code`, **bold** and \\(x^2 + y\\).

- one
- two

1. first
2. second

```bash
pixi run molo load
```

| a | b |
|---|---|
| 1 | 2 |

![fig](https://x/y.png)
"""


def balanced(html: str) -> bool:
    stack = []
    for m in re.finditer(r"<!-- (/?)wp:([\w-]+)[^>]*?(/?)-->", html):
        close, name, selfclose = m.groups()
        if selfclose:
            continue
        if close:
            if not stack or stack.pop() != name:
                return False
        else:
            stack.append(name)
    return not stack


def test_blocks_open_and_close_and_math_survives():
    out = markdown_to_blocks(DOC)
    assert balanced(out)
    assert '<!-- wp:heading {"anchor":"top"} -->' in out and 'id="top"' in out
    assert "\\(x^2 + y\\)" in out
    assert '<!-- wp:list {"ordered":true} -->' in out and "<code>pixi run molo load</code>" in out
    assert "wp:table" in out and 'wp:image' in out


def test_deterministic():
    assert markdown_to_blocks(DOC) == markdown_to_blocks(DOC)


def test_nested_list_is_refused():
    with pytest.raises(RenderError):
        markdown_to_blocks("- a\n  - b\n")


def test_unsupported_markdown_is_a_clean_error(gate_template=None):
    from molosite.sync import SyncError, render_generated  # noqa: F401
    with pytest.raises(RenderError):
        markdown_to_blocks("> quote\n")
