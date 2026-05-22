#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-25
# @description: Universal loader for different file types and web sources.Automatically selects appropriate LangChain loader.

import os
os.environ.setdefault("USER_AGENT", "MiniAgent/0.1.0")
from typing import List
from urllib.parse import urlparse

from langchain_core.documents import Document
import chardet

# HTML / Web
from langchain_community.document_loaders import (
    WebBaseLoader,
    BSHTMLLoader,
    RecursiveUrlLoader,
    SitemapLoader,
)

# Files
from langchain_community.document_loaders import (
    PyPDFium2Loader,
    CSVLoader,
    JSONLoader
)
from langchain_docling.loader import DoclingLoader

class SmartDocumentLoader:
    """
    Universal loader for different file types and web sources.
    Automatically selects appropriate LangChain loader.
    """

    def __init__(self, source: str):
        self.source = source

    # -------------------------
    # Public API
    # -------------------------
    def load(self) -> List[Document]:
        """
        Load documents based on source type.
        """
        if self._is_url(self.source):
            return self._load_web(self.source)
        else:
            return self._load_file(self.source)

    # -------------------------
    # URL Handling
    # -------------------------
    def _load_web(self, url: str) -> List[Document]:
        """
        Handle online sources.
        """

        # Sitemap
        if url.endswith("sitemap.xml"):
            loader = SitemapLoader(url)
            return loader.load()

        # Recursive
        if url.endswith("/") or "recursive=true" in url:
            loader = RecursiveUrlLoader(url)
            return loader.load()

        # Default Web page
        loader = WebBaseLoader(url)
        return loader.load()

    # -------------------------
    # File Handling
    # -------------------------
    def _load_file(self, path: str) -> List[Document]:
        """
        Handle local files.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found")

        ext = os.path.splitext(path)[1].lower()

        if ext in [".html", ".htm"]:
            loader = BSHTMLLoader(path)

        elif ext == ".pdf":
            loader = PyPDFium2Loader(path)

        elif ext == ".csv":
            loader = CSVLoader(path)

        elif ext == ".json":
            loader = JSONLoader(path)

        elif ext == ".txt":
            return self._load_txt_auto_encoding(path)

        # Office / rich docs
        elif ext in [".docx", ".pptx", ".doc", ".ppt"]:
            loader = DoclingLoader(path)

        else:
            raise ValueError(f"Unsupported file type: {ext}")

        return loader.load()

    def _load_txt_auto_encoding(self,file_path: str) -> List[Document]:
        # 1. Binary file reading and encoding detection
        with open(file_path, "rb") as f:
            raw_data = f.read()
            detect_result = chardet.detect(raw_data)
            encoding = detect_result["encoding"] or "gbk"
        
        # 2. Read according to the detection code and convert to UTF-8 content.
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()  # After reading, it is automatically converted to a Python Unicode string (which is essentially UTF-8).
        except:
            # fallback: Ignore encoding errors during reading
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        
        # 3. Construct a Document object (in the same format as the TextLoader output).
        return [Document(page_content=content, metadata={"source": file_path, "original_encoding": encoding})]

    # -------------------------
    # Helpers
    # -------------------------
    @staticmethod
    def _is_url(source: str) -> bool:
        parsed = urlparse(source)
        return parsed.scheme in ("http", "https")
    
if __name__ == "__main__":
    # online source
    url_loader = SmartDocumentLoader("http://www.wfcoding.com/articles/practice/0115/index.html")
    print(url_loader.load())

    # pdf file
    file_loader = SmartDocumentLoader("./data/test/中华人民共和国公司法_20231229.pdf")
    print(file_loader.load())

    # docx file
    doc_loader = SmartDocumentLoader("./data/test/ff8081818c9108eb018cb6922f750c07_中华人民共和国公司法_20231229.docx")   
    print(doc_loader.load())

    # csv file
    csv_loader = SmartDocumentLoader("./data/test/metadata.csv")
    print(csv_loader.load())