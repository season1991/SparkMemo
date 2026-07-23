"""生成 openapi/cross_table_fill.json（仅含 cross-table-fill 模块路径与对应 schemas）。"""
from __future__ import annotations

import json
from pathlib import Path

from app.main import app


def main() -> None:
    schema = app.openapi()

    keep_paths = {k: v for k, v in schema["paths"].items() if k.startswith("/api/cross-table-fill")}
    schema["paths"] = keep_paths

    # 收集引用的 schema 名（transitive 用 BFS）
    referenced: set[str] = set()
    visited: set[str] = set()
    frontier: set[str] = set()

    def collect(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "$ref" and isinstance(v, str) and v.startswith("#/components/schemas/"):
                    name = v.split("/")[-1]
                    referenced.add(name)
                    frontier.add(name)
                else:
                    collect(v)
        elif isinstance(obj, list):
            for item in obj:
                collect(item)

    for p in keep_paths.values():
        collect(p)

    all_schemas = schema["components"]["schemas"]
    # BFS 展开 transitive refs
    while frontier:
        nxt: set[str] = set()
        current_frontier = list(frontier)
        for name in current_frontier:
            if name in visited or name not in all_schemas:
                continue
            visited.add(name)
            collect(all_schemas[name])
            for s in all_schemas.keys():
                if s in referenced and s not in visited:
                    nxt.add(s)
        frontier = nxt - visited

    schema["components"]["schemas"] = {
        n: all_schemas[n]
        for n in sorted(all_schemas)
        if n in referenced
        or n.startswith("CrossTableFill")
        or n in ("HTTPValidationError", "ValidationError")
    }

    schema["info"]["title"] = "SparkMemo Cross-Table Fill API"
    schema["info"]["version"] = "0.6.0"
    schema["info"]["description"] = "跨表数据填充模块 API 契约（v0.6.0）"

    out = Path("openapi/cross_table_fill.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"paths: {list(schema['paths'].keys())}")
    print(f"schemas: {list(schema['components']['schemas'].keys())}")
    print(f"written: {out}")


if __name__ == "__main__":
    main()
