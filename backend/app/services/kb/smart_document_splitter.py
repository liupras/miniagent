#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun (Enhanced by Gemini)
# @date    : 2026-02-25
# @description: Automatically divide various document types into chunks.


import json
import re
from typing import List
from copy import deepcopy

from langchain_core.documents import Document
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
    RecursiveJsonSplitter,
    Language,
)

from bs4 import BeautifulSoup
from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound

class SmartDocumentSplitter:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # =====================================
    # Public API
    # =====================================
    def split_documents(self, docs: List[Document]) -> List[Document]:
        results = []
        for doc in docs:
            content = doc.page_content
            metadata = deepcopy(doc.metadata) or {}
            doc_type = self._detect_type(content, metadata)

            # HTML preprocessing: After extracting the text, process it as plain text.
            if doc_type == "html":
                content = self._extract_html_main(content)
                doc_type = "text"

            split_docs = []
            if doc_type == "markdown":
                split_docs = self._split_markdown(content, metadata)
            elif doc_type == "json":
                split_docs = self._split_json(content, metadata)
            elif doc_type == "code":
                texts = self._split_code(content, metadata)
                split_docs = [Document(page_content=t, metadata=metadata) for t in texts]
            else:
                texts = self._split_text(content, metadata)
                split_docs = [Document(page_content=t, metadata=metadata) for t in texts]

            results.extend(split_docs)
        return results

    # =====================================
    # Type Detection & Language Mapping
    # =====================================
    def _detect_type(self, content: str, metadata: dict) -> str:
        source = metadata.get("source", "").lower()
        if source.endswith(".md"): return "markdown"
        if source.endswith(".json"): return "json"
        if source.endswith((".html", ".htm")): return "html"

        try:
            json.loads(content)
            return "json"
        except: pass

        if re.search(r"^#{1,6}\s", content, re.MULTILINE): return "markdown"
        if "<html" in content.lower(): return "html"

        try:
            guess_lexer(content)
            return "code"
        except ClassNotFound: pass

        return "text"

    def _get_langchain_language(self, content: str) -> Language:
        """Dynamically mapping Pygments recognition results to LangChain Language enumerations"""
        try:
            lexer = guess_lexer(content)            
            # Get all aliases of this lexer and match them.
            aliases = lexer.aliases 
        except:
            return Language.PYTHON

        mapping = {
            "python": Language.PYTHON,
            "java": Language.JAVA,
            "javascript": Language.JS,
            "js": Language.JS,
            "typescript": Language.TS,
            "ts": Language.TS,
            "cpp": Language.CPP,
            "c++": Language.CPP,
            "go": Language.GO,
            "rust": Language.RUST,      
            "ruby": Language.RUBY,
            "php": Language.PHP,
            "csharp": Language.CSHARP,
            "c#": Language.CSHARP,
        }

        for alias in aliases:
            if alias in mapping:
                return mapping[alias]
        return Language.PYTHON

    # =====================================
    # Specialized Splitters
    # =====================================
    def _extract_html_main(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n")

    def _split_markdown(self, content: str, metadata: dict) -> List[Document]:
        headers = [("#", "h1"), ("##", "h2"), ("###", "h3")]
        splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers)
        docs = splitter.split_text(content)
        recursive = RecursiveCharacterTextSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        return recursive.split_documents(docs)
    
    def _split_json(self, content: str, metadata: dict) -> List[Document]:
        try:
            # Attempting to parse a JSON string
            data = json.loads(content)
            splitter = RecursiveJsonSplitter(max_chunk_size=self.chunk_size)
            
            # Using create_documents is more robust
            # It automatically handles content serialization and chunking.
            docs = splitter.create_documents(texts=[data])

            # Processing metadata and JSON paths
            results = []
            for doc in docs:
                new_meta = deepcopy(metadata)
                # Record the path of this block in the original JSON (if any).
                if doc.metadata and "path" in doc.metadata:
                    new_meta["json_path"] = doc.metadata.get("path")
                results.append(
                    Document(page_content=doc.page_content, metadata=new_meta)
                )
            return results
            
        except Exception as e:
            # Backup solution: If special JSON splitting fails (e.g., formatting errors or index overflow), it degenerates into regular text splitting.
            print(f"⚠️ JSON splitting failed, falling back to text split: {e}")
            texts = self._split_text(content, metadata)
            return [Document(page_content=t, metadata=metadata) for t in texts]


    def _split_code(self, content: str, metadata: dict) -> List[str]:
        target_lang = self._get_langchain_language(content)
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=target_lang,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        return splitter.split_text(content)

    def _split_text(self, content: str, metadata: dict) -> List[str]:
        separators = ["\n\n", "\n", "。", "！", "？", ". ", " ", ""]
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap, separators=separators
        )
        return splitter.split_text(content)

# =====================================
# Main Testing
# =====================================
if __name__ == "__main__":
    splitter = SmartDocumentSplitter(chunk_size=200, chunk_overlap=20)

    test_docs = [
        Document(
            page_content="<html><body><nav>Menu</nav><h1>Title</h1><p>Hello World!</p></body></html>",
            metadata={"source": "index.html"}
        ),
        Document(
            page_content="# Header 1\n## Header 2\nThis is a markdown content that needs to be split by headers.",
            metadata={"source": "notes.md"}
        ),
        Document(
            page_content="SELECT id, name FROM users WHERE age > 18 ORDER BY created_at DESC;",
            metadata={"source": "query.sql"}
        ),
        Document(
            page_content='fn main() {\n    println!("Hello Rust!");\n    let x = 5;\n}',
            metadata={"source": "main.rs"}
        ),
        Document(
            page_content=json.dumps({"user": {"id": 1, "profile": {"bio": "A long bio that might need splitting..."}}}),
            metadata={"source": "data.json"}
        ),
        Document(
            page_content=json.dumps({"user": {"id": 2, "profile": {"bio": "A long bio that might need splitting...",
                                                                   "settings": {"theme": "dark", "notifications": True}}}}),
            metadata={"source": "data.json"}
        )
    ]

    print(f"--- Starting Split Test (Total Input: {len(test_docs)} docs) ---")
    final_chunks = splitter.split_documents(test_docs)
    
    for i, res in enumerate(final_chunks):
        print(f"\nChunk {i+1} | Source: {res.metadata.get('source')} | Type: {type(res)}")
        print(f"Content: {res.page_content[:100]}...")

    # Validate final type
    assert all(isinstance(d, Document) for d in final_chunks), "Error: Not all outputs are Document objects!"
    print("\n✅ Test Passed: All chunks are validated as List[Document]")