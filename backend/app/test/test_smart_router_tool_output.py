import asyncio
import json
from types import SimpleNamespace

from app.runtime.agent.tool_builder import _build_smart_router_tool


class _SmartRouter:
    async def query(self, *, query, kb_ids):
        assert query == "著作权保护期限"
        assert kb_ids == [4]
        return SimpleNamespace(
            confidence="high",
            warning=None,
            chunks=[
                SimpleNamespace(
                    text="第十条 测试内容。",
                    final_score=0.95154,
                    metadata={
                        "citation": {
                            "doc_id": 1,
                            "chunk_id": 25,
                            "filename": "中华人民共和国著作权法.txt",
                            "source": "中华人民共和国著作权法",
                            "article_no": "第十条",
                        },
                        "parent_id": 99,
                    },
                )
            ],
        )


def test_smart_router_exposes_only_public_citation_metadata():
    tool_orm = SimpleNamespace(
        name="law_search",
        description="Search laws",
        config={"allowed_kb_ids": [4]},
        tool_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    tool = _build_smart_router_tool(tool_orm, tool_orm.config, _SmartRouter())

    raw = asyncio.run(tool.ainvoke({"query": "著作权保护期限"}))
    result = json.loads(raw)
    chunk = result["chunks"][0]

    assert "source" not in chunk
    assert "metadata" not in chunk
    assert chunk["citation"]["source"] == "中华人民共和国著作权法"
    assert chunk["citation"]["article_no"] == "第十条"
    assert chunk["score"] == 0.9515
