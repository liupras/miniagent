#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-16
# @description: Abstract base class for small-to-big chunking processors.
#
#   Subclasses must implement two domain-specific hooks:
#     _split_to_parents()    — how to cut raw pages into parent-level Documents
#     _split_to_childs()     - how to cut raw pages into child-level Documents
#     _build_chunk_metadata() — what _extra_metadata to attach to each child chunk


from datetime import datetime
from typing import List, Tuple
from typing import final
from copy import deepcopy

from langchain_core.documents import Document
from dataclasses import dataclass

from app.infra.db.database  import ParentChunk, Chunk
from app.utils.hash import sha256_hash
from app.utils.tokens import estimate_tokens as count_tokens

from app.services.kb.smart_document_splitter import SmartDocumentSplitter

@dataclass
class ChunkConfig:
    """Configuring the parent and child chunkers (packing all chunking parameters)"""
    parent_chunk_size: int = 1250
    parent_overlap: int = 150
    child_chunk_size: int = 250
    child_overlap: int = 50

class SmallToBigProcessor:
    """
    General small-to-big processor base class.

    Subclasses may override ONLY:
        _split_to_parents()
        _split_to_childs()
        _build_chunk_metadata()

    All other methods are final.
    """

    _final_methods = {
        "process",
        "_make_parent_chunk",
        "_make_child_chunk",
    }

    # ─────────────────────────────────────────────
    # Prevent overriding final methods
    # ─────────────────────────────────────────────

    def __init_subclass__(cls):
        for name in cls._final_methods:
            if name in cls.__dict__:
                raise TypeError(f"Method '{name}' cannot be overridden")
        super().__init_subclass__()
 
    # ─────────────────────────────────────────────
    # Main pipeline (NOT overridable)
    # ─────────────────────────────────────────────

    @final
    def process(
        self, structured_docs: List[Document],
        kb_id:             int,
        doc_id:            int,
        config: ChunkConfig
    ) -> Tuple[List[ParentChunk], List[Chunk]]:
                
        parent_docs = self._split_to_parents(structured_docs,config)

        parent_chunks: List[ParentChunk] = []
        small_chunks:  List[Chunk]       = []
        global_child_idx = 0

        for idx, doc in enumerate(parent_docs):
            parent_hash = sha256_hash(doc.page_content)
            parent = self._make_parent_chunk(doc, idx, parent_hash,kb_id,doc_id)
            parent_chunks.append(parent)

            child_docs = self._split_to_childs([doc], config=config)
            for i, child_doc in enumerate(child_docs):
                meta = self._build_chunk_metadata(doc, idx, parent_hash)   
                meta["relative_index"] = i # The location recorded inside the parent block             
                child = self._make_child_chunk(child_doc, global_child_idx, meta, kb_id, doc_id)
                small_chunks.append(child)                
                global_child_idx += 1

        return parent_chunks, small_chunks

    # ─────────────────────────────────────────────
    # Overridable hooks
    # ─────────────────────────────────────────────

    def _split_to_parents(
        self, structured_docs: List[Document],
        config: ChunkConfig
    ) -> List[Document]:
        """
        Default parent splitting strategy.
        Subclasses MAY override.
        """
        splitter = SmartDocumentSplitter(
            chunk_size    = config.parent_chunk_size,
            chunk_overlap = config.parent_overlap,
        )
        return splitter.split_documents(structured_docs)
    
    def _split_to_childs(
        self, structured_docs: List[Document],
        config: ChunkConfig
    ) -> List[Document]:
        splitter = SmartDocumentSplitter(
            chunk_size    = config.child_chunk_size,
            chunk_overlap = config.child_overlap,
        )
        return splitter.split_documents(structured_docs)

    def _build_chunk_metadata(
        self,
        parent_doc:   Document,
        parent_index: int,
        parent_hash:  str,        
    ) -> dict:
        """
        Default metadata builder.
        Subclasses MAY override.
        """

        meta = deepcopy(parent_doc.metadata) or {}

        meta.update({
            "parent_index": parent_index,
            "parent_hash":  parent_hash,
            "content_type": meta.get("type", "structured_element"),
        })

        return meta

    # ─────────────────────────────────────────────
    # Shared helpers (NOT overridable)
    # ─────────────────────────────────────────────

    @final
    def _make_parent_chunk(
        self, doc: Document, idx: int, parent_hash: str,
        kb_id:int,doc_id:int
    ) -> ParentChunk:

        text = doc.page_content

        return ParentChunk(
            kb_id       = kb_id,
            doc_id      = doc_id,
            hash_value  = parent_hash,
            text        = text,
            chunk_index = idx,
            char_count  = len(text),
            token_count = count_tokens(text),
            created_at  = datetime.now(),
        )

    @final
    def _make_child_chunk(
        self, child_doc: Document, idx: int, meta: dict,
        kb_id,doc_id
    ) -> Chunk:

        text       = child_doc.page_content
        chunk_hash = sha256_hash(text)

        # meta["hash_value"] = chunk_hash

        chunk = Chunk(
            kb_id       = kb_id,
            doc_id      = doc_id,
            parent_id   = None,
            hash_value  = chunk_hash,
            text        = text,
            chunk_index = idx,
            char_count  = len(text),
            created_at  = datetime.now(),
        )

        chunk._extra_metadata = meta

        return chunk
    

# ─────────────────────────────────────────────────────────────────────────────
# Stand-alone test  (python small_to_big.py)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("===== 开始测试 SmallToBigProcessor 类 =====")

    test_docs = [
        Document(
            page_content=(
                "人工智能（Artificial Intelligence，AI）是一门旨在使计算机系统能够模拟、"
                "延伸和扩展人类智能的技术科学。它涵盖了机器学习、自然语言处理、计算机视觉等多个领域，"
                "近年来随着大数据和算力的提升，AI技术得到了飞速发展。"
            ),
            metadata={"type": "paragraph", "source": "test_doc_1", "page": 1},
        ),
        Document(
            page_content=(
                "LangChain 是一个用于构建基于大语言模型的应用程序的框架，"
                "它提供了丰富的工具和组件，支持文档处理、链调用、智能体开发等功能。"
                "在知识库构建场景中，LangChain 的文档分割能力尤为重要。"
            ),
            metadata={"type": "paragraph", "source": "test_doc_1", "page": 2},
        ),
    ]

    # Bug fix 4: SmallToBigProcessor takes no constructor arguments;
    # kb_id, doc_id, chunk sizes are passed to process() via config
    processor = SmallToBigProcessor()

    config = ChunkConfig(
        parent_chunk_size=500,
        parent_overlap=100,
        child_chunk_size=100,
        child_overlap=10,
    )

    # Bug fix 5: process() requires kb_id, doc_id, and config arguments
    parent_chunks, small_chunks = processor.process(
        structured_docs=test_docs,
        kb_id=1001,
        doc_id=2001,
        config=config,
    )

    print("\n--- 验证父分片（ParentChunk）结果 ---")
    assert len(parent_chunks) > 0, "父分片数量应为正数"
    print(f"父分片数量：{len(parent_chunks)}")

    for idx, parent in enumerate(parent_chunks):
        assert parent.kb_id    == 1001,  f"父分片{idx}的kb_id错误"
        assert parent.doc_id   == 2001,  f"父分片{idx}的doc_id错误"
        assert parent.chunk_index == idx, f"父分片{idx}的index错误"
        assert parent.char_count  == len(parent.text), f"父分片{idx}的字符数错误"
        assert parent.hash_value  == sha256_hash(parent.text), f"父分片{idx}的哈希值错误"
        print(f"  父分片{idx}：chars={parent.char_count}（验证通过）")

    print("\n--- 验证小分片（Chunk）结果 ---")
    assert len(small_chunks) > 0, "小分片数量应为正数"
    print(f"小分片总数量：{len(small_chunks)}")

    for small in small_chunks:
        pidx        = small._extra_metadata.get("parent_index")
        parent_hash = small._extra_metadata.get("parent_hash")

        assert small.kb_id  == 1001,     "小分片kb_id错误"
        assert small.doc_id == 2001,     "小分片doc_id错误"
        assert pidx         is not None, "小分片未关联父分片index"
        assert parent_hash  == parent_chunks[pidx].hash_value, "小分片父哈希值不匹配"
        assert small.char_count == len(small.text), "小分片字符数错误"
        print(f"  小分片（父索引{pidx}）：chars={small.char_count}（验证通过）")

    print("\n===== 所有测试用例执行通过 =====")
