"""Собирает закладку (bookmarklet) из JS-сборщика: python tools/collectors/make_bookmarklet.py mvideo|goldapple|detmir|chitaigorod"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote


def build(name: str) -> str:
    source = (Path(__file__).parent / f"{name}.js").read_text(encoding="utf-8")
    # Сборщики пишутся без ASI-зависимостей: каждая инструкция завершается «;», комментарии только целыми строками.
    lines = [line.strip() for line in source.splitlines() if line.strip() and not line.strip().startswith("//")]
    return "javascript:" + quote(" ".join(lines), safe="(){}[];,.=>!?:'\"*+-_/<>|&$`@")


if __name__ == "__main__":
    store = sys.argv[1] if len(sys.argv) > 1 else "mvideo"
    print(build(store))
