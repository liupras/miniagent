#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-16
# @description: Legal-domain implementation of SmallToBigProcessor.

import re
from typing import List
from copy import deepcopy

from langchain_core.documents import Document
   
from app.services.kb.small_to_big_base import SmallToBigProcessor, ChunkConfig
from .normalize_text import normalize_law_text

class LawSmallToBigProcessor(SmallToBigProcessor):
    """
    Legal structure is divided into sections: Article → Paragraph → Item → Sentence.
    """

    # ─────────────────────────────────────────────
    # Pattern Definition
    # ─────────────────────────────────────────────

    ARTICLE_PATTERN = re.compile(r"\r?\n(?=[ \t\u3000]*第\s*[零一二三四五六七八九十百千万0-9]+\s*条)")

    ITEM_PATTERN = re.compile(
        r"(\([一二三四五六七八九十]+\)|（[一二三四五六七八九十]+）|[一二三四五六七八九十]+、|\d+\.)"
    )

    SENTENCE_SPLIT = re.compile(r"(。|.|；|;|！|!|？|\?)")

    ARTICLE_NO_PATTERN = re.compile(r"第\s*([零一二三四五六七八九十百千万0-9]+)\s*条")

    ARTICLE_REF_PATTERN = re.compile(r"第\s*[零一二三四五六七八九十百千万0-9]+\s*条")

    # ─────────────────────────────────────────────
    # Rewrite: Parent block segmentation (article/paragraph level)
    # ─────────────────────────────────────────────

    def _split_to_parents(
        self,
        structured_docs: List[Document],
        config: ChunkConfig
    ) -> List[Document]:

        parents: List[Document] = []

        for doc in structured_docs:

            text = normalize_law_text(doc.page_content)

            articles = re.split(self.ARTICLE_PATTERN,text)

            for art_text in articles:
                if not art_text.strip(): continue
                chunks = self._legal_hierarchical_split(art_text.strip(), config.parent_chunk_size)
                parents.extend([Document(page_content=c, metadata=deepcopy(doc.metadata)) for c in chunks])
        return parents
    
    # ─────────────────────────────────────────────
    # Rewriting: Sub-block segmentation (item/sentence level)
    # ─────────────────────────────────────────────
    def _split_to_childs(self, structured_docs: List[Document], config: ChunkConfig) -> List[Document]:
        """
        The child block starts from the content of the parent block and further refines it to the sentence level.
        """
        childs = []
        for doc in structured_docs:
            chunks = self._legal_hierarchical_split(doc.page_content, config.child_chunk_size)
            childs.extend([Document(page_content=c, metadata=deepcopy(doc.metadata)) for c in chunks])
        return childs
    
    # ─────────────────────────────────────────────
    # Core: General legal hierarchy recursive segmenter
    # ─────────────────────────────────────────────
    def _legal_hierarchical_split(self, text: str, max_size: int, level: str = "paragraph") -> List[str]:
        if len(text) <= max_size:
            return [text]

        # 1. Paragraph level
        if level == "paragraph":
            parts = [p.strip() for p in re.split(r"[\r\n]+", text) if p.strip()]
            return self._recursive_process(parts, max_size, "item")

        # 2. Item level
        elif level == "item":
            parts = self._split_by_pattern(text, self.ITEM_PATTERN)
            if len(parts) <= 1: # The fact that it wasn't cut open means there's no "item," so it's downgraded to a sentence.
                return self._legal_hierarchical_split(text, max_size, "sentence")
            return self._recursive_process(parts, max_size, "sentence")

        # 3. Sentence level
        elif level == "sentence":
            return self._split_sentence_by_size(text, max_size)

        return [text]
    
    def _recursive_process(self, parts: List[str], max_size: int, next_level: str) -> List[str]:
        res = []
        current_buffer = []
        current_length = 0

        for p in parts:
            p_len = len(p)
            
            # Case 1: A single fragment has already exceeded max_size
            if p_len > max_size:
                # First, store the existing contents of the buffer into res.
                if current_buffer:
                    res.append("\n".join(current_buffer)) 
                    current_buffer = []
                    current_length = 0
                
                # Perform finer-grained recursive segmentation on this extremely long fragment.
                res.extend(self._legal_hierarchical_split(p, max_size, next_level))
            
            # Case 2: The current segment plus the buffer exceeds the max_size.
            elif current_length + p_len > max_size:
                # The buffer is full; store res.
                if current_buffer:
                    res.append("\n".join(current_buffer))
                
                # Reset the buffer and begin storing the current segment.
                current_buffer = [p]
                current_length = p_len
            
            # Scenario 3: It can continue to accumulate.
            else:
                current_buffer.append(p)
                current_length += p_len

        # Finally, process the remaining content in the buffer.
        if current_buffer:
            res.append("\n".join(current_buffer))
            
        return res
    
    #─────────────────────────────────────────────
    # General pattern split
    # ─────────────────────────────────────────────
    def _split_by_pattern(self, text, pattern):

        matches = list(pattern.finditer(text))
        if not matches:
            return [text]
        parts = []
        for i, m in enumerate(matches):
            start = m.start()
            end = (
                matches[i + 1].start()
                if i + 1 < len(matches)
                else len(text)
            )

            parts.append(text[start:end].strip())

        return parts

    def _split_sentence_by_size(self, text: str, max_size: int) -> List[str]:
        """
        Specialized sentence-level segmentation: While satisfying the max_size, try to ensure the sentence is complete.
        """
        parts = self.SENTENCE_SPLIT.split(text)
        sentences = []
        current = ""

        for i in range(0, len(parts), 2):
            sent = parts[i]
            punct = parts[i+1] if i+1 < len(parts) else ""
            full_sent = sent + punct
            
            if len(current) + len(full_sent) <= max_size:
                current += full_sent
            else:
                if current: sentences.append(current.strip())
                # If a single sentence is still too long, force segmentation.
                if len(full_sent) > max_size:
                    sentences.extend(self._force_split(full_sent, max_size))
                    current = ""
                else:
                    current = full_sent
        if current: sentences.append(current.strip())
        return sentences
    
    #────────────────────
    # Forced segmentation (fallback)
    # ────────────────────
    def _force_split(self, text, max_size):

        return [
            text[i:i + max_size]
            for i in range(0, len(text), max_size)
        ]

    # ─────────────────────────────────────────────
    # Metadata enhancement
    # ─────────────────────────────────────────────

    def _build_chunk_metadata(
        self,
        parent_doc,
        parent_index,
        parent_hash
    ):

        meta = deepcopy(parent_doc.metadata) or {}

        text = parent_doc.page_content

        # 1. Extract the current legal article number (e.g., "one")
        article_no = self._extract_article_no(text)
        # 2. Retrieve all cited legal article numbers (e.g., ["Article 10", "Article 1", "Article 20"])
        refs = list(set(self.ARTICLE_REF_PATTERN.findall(text)))
        # 3. Filtering logic
        if article_no:
            refs = list(set([
                ref for ref in refs 
                if self._normalize_ref(ref) != article_no
            ]))            
        else:
            refs = list(set([ref.strip() for ref in refs]))

        meta.update({
            "parent_index": parent_index,
            "parent_hash": parent_hash,
            "content_type": "law",
            "article_no": article_no,
            "refer_articles": refs,
        })

        return meta
    
    def _normalize_ref(self, ref_str):
        # Remove "第", "条", and spaces, and convert all text to plain content for comparison.
        return re.sub(r"[第条\s]", "", ref_str)

    # ─────────────────────────────────────────────
    # Extract article number
    # ─────────────────────────────────────────────

    def _extract_article_no(self, text):

        m = re.search(self.ARTICLE_NO_PATTERN,text)
        return m.group(1) if m else None

# ─────────────────────────────────────────────────────────────────────────────
# Stand-alone test (python law_small_to_big_processor.py)
# ─────────────────────────────────────────────────────────────────────────────

def test_with_fake_data():

    from langchain_core.documents import Document

    print("===== 开始测试 LawSmallToBigProcessor =====")

    # ─────────────────────────────────────────────
    # 构造复杂法律文本（覆盖所有情况）
    # ─────────────────────────────────────────────

    test_text = """
第一条 为了规范合同管理，保护当事人合法权益，制定本法。
第二条 本法适用于中华人民共和国境内的合同关系。本条所称合同包括买卖合同、服务合同等。
第三条 合同当事人应当遵循公平原则确定各方的权利和义务。
第四条 有下列情形之一的，合同无效：（一）以欺诈、胁迫手段订立合同；（二）恶意串通，损害国家利益；（三）违反法律、行政法规的强制性规定。
第五条 当事人一方违约的，应当承担违约责任，包括继续履行、采取补救措施或者赔偿损失。违约责任的承担方式可以由当事人约定。
第六条 本条引用测试：依照第三条、第四条的规定执行。
第七条 超长句测试：{}。
""".format("这是一个非常长的句子" * 100)  # 强制触发句子切分

    test_docs = [
        Document(
            page_content=test_text,
            metadata={"source": "law_test", "type": "law"}
        )
    ]

    # ─────────────────────────────────────────────
    # 初始化 Processor
    # ─────────────────────────────────────────────

    processor = LawSmallToBigProcessor()

    config = ChunkConfig(
        parent_chunk_size=300,   # 故意调小，触发多级切分
        parent_overlap=50,
        child_chunk_size=120,
        child_overlap=20,
    )

    # ─────────────────────────────────────────────
    # 执行处理
    # ─────────────────────────────────────────────

    parent_chunks, child_chunks = processor.process(
        structured_docs=test_docs,
        kb_id=1,
        doc_id=1,
        config=config
    )

    # ─────────────────────────────────────────────
    # 测试 1：父分片基本验证
    # ─────────────────────────────────────────────

    print("\n--- 测试1：父分片 ---")

    assert len(parent_chunks) > 0, "❌ 父分片为空"

    for i, p in enumerate(parent_chunks):
        print(f"[Parent {i}] chars={p.char_count}")

        assert p.char_count <= config.parent_chunk_size + 20, \
            "❌ 父分片超过限制（未正确切分）"

    print("✅ 父分片测试通过")

    # ─────────────────────────────────────────────
    # 测试 2：是否按“条”切分
    # ─────────────────────────────────────────────

    print("\n--- 测试2：条切分 ---")

    article_count = sum(
        1 for p in parent_chunks
        if "第" in p.text and "条" in p.text
    )

    assert article_count >= 5, "❌ 条切分失败（条数量异常）"

    print(f"检测到条数量：{article_count}")
    print("✅ 条切分测试通过")

    # ─────────────────────────────────────────────
    # 测试 3：项切分（（一）（二））
    # ─────────────────────────────────────────────

    print("\n--- 测试3：项切分 ---")

    item_detected = any(
        "（一）" in p.text or "（二）" in p.text
        for p in parent_chunks
    )

    assert item_detected, "❌ 未识别项结构"

    print("✅ 项切分测试通过")

    # ─────────────────────────────────────────────
    # 测试 4：句切分（长句）
    # ─────────────────────────────────────────────

    print("\n--- 测试4：长句切分 ---")

    long_chunks = [
        p for p in parent_chunks
        if len(p.text) > config.parent_chunk_size
    ]

    assert len(long_chunks) == 0, "❌ 长句未被正确切分"

    print("✅ 长句切分测试通过")

    # ─────────────────────────────────────────────
    # 测试 5：metadata（核心）
    # ─────────────────────────────────────────────

    print("\n--- 测试5：metadata ---")

    sample = child_chunks[0]._extra_metadata

    assert "article_no" in sample, "❌ 缺少 article_no"
    assert "refer_articles" in sample, "❌ 缺少 refer_articles"

    print("metadata示例：")
    print(sample)

    print("✅ metadata测试通过")

    # ─────────────────────────────────────────────
    # 测试 6：引用条识别（Graph关键）
    # ─────────────────────────────────────────────

    print("\n--- 测试6：引用条识别 ---")

    found_ref = False

    for c in child_chunks:
        refs = c._extra_metadata.get("refer_articles", [])
        if "第三条" in refs or "第四条" in refs:
            found_ref = True
            break

    assert found_ref, "❌ 引用条未识别"

    print("✅ 引用条识别测试通过")

    # ─────────────────────────────────────────────
    # 测试 7：child chunk 关联 parent
    # ─────────────────────────────────────────────

    print("\n--- 测试7：父子关联 ---")

    for c in child_chunks:
        meta = c._extra_metadata

        assert meta.get("parent_index") is not None
        assert meta.get("parent_hash") is not None

    print("✅ 父子关联测试通过")

    # ─────────────────────────────────────────────
    # 打印部分结果（人工检查）
    # ─────────────────────────────────────────────

    print("\n--- 示例输出（前5个父分片）---")

    for i, p in enumerate(parent_chunks[:5]):
        print(f"\n[Parent {i}]")
        print(p.text[:200])

    print("\n===== ✅ 所有测试通过 =====")


def test_with_file():
    # 1. 模拟环境与配置
    config = ChunkConfig(parent_chunk_size=1000, child_chunk_size=200)
    processor = LawSmallToBigProcessor()
    
    # 模拟从 metadata.csv 读取数据
    law_id = "ff8081818c9108eb018cb6922f750c07"
    mock_metadata = {
        "id": law_id,
        "title": "中华人民共和国公司法",
        "office": "全国人民代表大会常务委员会",
        "publish_date":"2023/12/29",
        "expiry_date":"",
        "implement_date":"2024/7/1",
        "status":"有效",
        "type":"法律"
    }

    # 2. 读取上传的 txt 文件
    file_path = "D:/miniagent/backend/data/test_doc/ff8081818c9108eb018cb6922f750c07_中华人民共和国公司法_20231229.txt"
    with open(file_path, 'r', encoding='utf-8') as f:
        full_text = f.read()

    # 3. 构造输入
    doc = Document(page_content=full_text, metadata=mock_metadata)
    
    # 4. 执行完整切分流程
    # kb_id=1, doc_id=101
    parent_chunks, small_chunks = processor.process([doc], kb_id=1, doc_id=101, config=config)

    print(f"--- 切分结果报告 ---")
    print(f"父块数量: {len(parent_chunks)}")
    print(f"子块数量: {len(small_chunks)}")

    # 5. 逻辑验证 1: 条号提取是否准确
    for p in parent_chunks[5:10]: # 抽查中间几条
        print(f"索引 {p.chunk_index} | 条号: {processor._extract_article_no(p.text)} | 长度: {p.char_count}")

    # 6. 逻辑验证 2: 子块与父块的关联性
    # 检查第一个子块的元数据是否包含父块 Hash
    if small_chunks:
        sample_child = small_chunks[0]
        print(f"\n子块示例 (Index {sample_child.chunk_index}):")
        print(f"内容: {sample_child.text[:50]}...")
        print(f"关联元数据: {sample_child._extra_metadata}")
        
        # 验证 parent_hash 是否成功传递
        assert "parent_hash" in sample_child._extra_metadata
        assert sample_child._extra_metadata["content_type"] == "law"

    # 7. 逻辑验证 3: 预处理对“款/项”的影响
    # 检查是否存在包含“（一）”等项的子块
    item_chunks = [c for c in small_chunks if "（一）" in c.text]
    print(f"\n包含“项”级的子块数量: {len(item_chunks)}")
    if item_chunks:
        print(f"项级子块预览: {item_chunks[0].text}")


if __name__ == "__main__":
    test_with_fake_data()
    test_with_file()