import os
import json
import re
import pickle
import shutil
import subprocess
import html2text
import jieba
import logging
from pathlib import Path
from typing import Callable, List, Dict, Optional
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from src.services.library_manager import library_manager

# --- 移植常量 ---
SPLIT_HEURISTIC_THRESHOLD = 9
MIN_CONTENT_LENGTH = 30

class CHMProcessor:
    def __init__(self, chm_path: str, lib_id: str):
        self.chm_path = Path(chm_path)
        self.lib_id = lib_id

        # 路径配置
        self.lib_path = library_manager.get_library_path(lib_id)
        self.source_dir = self.lib_path / "chm_source"
        self.index_dir = self.lib_path / "vector_store"
        self.json_path = self.lib_path / "rules_data.json"

        # html2text 配置
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = True
        self.h2t.body_width = 0
        self.h2t.protect_links = True
        self.h2t.mark_code = True

    def extract_chm(self, progress_callback: Callable):
        """解压逻辑"""
        progress_callback(0.1, "正在解压 CHM 文件...")
        bin_7z = Path(os.getcwd()) / "bin" / "7za.exe"
        if not bin_7z.exists():
            bin_7z = "7z"

        if self.source_dir.exists():
            shutil.rmtree(self.source_dir)
        self.source_dir.mkdir(parents=True, exist_ok=True)

        cmd = [str(bin_7z), "x", str(self.chm_path), f"-o{self.source_dir}", "-y"]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    def analyze_top_levels(self) -> List[str]:
        """获取顶级目录供用户选择"""
        top_levels = []
        for item in self.source_dir.iterdir():
            if item.is_dir():
                top_levels.append(item.name)
        return sorted(top_levels)

    def run_processing(self, selected_folders: List[str], progress_callback: Callable):
        """执行核心处理流程"""
        progress_callback(0.2, "开始分析文档结构与分割...")

        all_documents = []
        files_to_process = []

        # 1. 收集文件
        for f in self.source_dir.glob("*.htm*"):
            if f.is_file(): files_to_process.append(f)
        for folder_name in selected_folders:
            folder_path = self.source_dir / folder_name
            if folder_path.exists():
                files_to_process.extend(folder_path.rglob("*.htm*"))

        total_files = len(files_to_process)
        if total_files == 0:
            raise ValueError("未找到任何 HTML 文件")

        # 2. 遍历处理
        for i, file_path in enumerate(files_to_process):
            if i % 20 == 0:
                progress = 0.2 + (i / total_files) * 0.6
                progress_callback(progress, f"处理中: {file_path.name}")

            docs = self._process_single_file(file_path)
            all_documents.extend(docs)

        # 3. 保存与索引
        progress_callback(0.85, f"正在生成索引 (共 {len(all_documents)} 个切片)...")
        self._save_and_index(all_documents)

        # 4. 完成
        library_manager.update_metadata(self.lib_id, doc_count=len(all_documents))
        shutil.rmtree(self.source_dir, ignore_errors=True)
        progress_callback(1.0, "处理完成！")

    def _process_single_file(self, file_path: Path) -> List[Document]:
        content = self._read_file_encoded(file_path)
        if not content: return []

        rel_path = file_path.relative_to(self.source_dir).as_posix()
        file_stem = file_path.stem

        # --- 算法移植核心: 级联判断 split_by ---
        split_tag = self._determine_split_tag(content)

        docs = []

        if split_tag:
            # --- 算法移植核心: 正则分割 ---
            docs = self._regex_split(content, split_tag, file_stem, rel_path)
        else:
            # 不分割，转 Markdown
            md_text = self._html_to_md(content)
            if len(md_text) > MIN_CONTENT_LENGTH:
                docs.append(Document(
                    page_content=md_text,
                    metadata={
                        "source": file_stem,
                        "title": file_stem,
                        "full_path": rel_path,
                        "is_chunk": False
                    }
                ))

        return docs

    def _determine_split_tag(self, html_content: str) -> Optional[str]:
        """级联阈值判断"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            h1_count = len(soup.find_all("h1"))
            if h1_count > SPLIT_HEURISTIC_THRESHOLD: return "h1"

            h2_count = len(soup.find_all("h2"))
            if h2_count > SPLIT_HEURISTIC_THRESHOLD: return "h2"

            h3_count = len(soup.find_all("h3"))
            if h3_count > SPLIT_HEURISTIC_THRESHOLD: return "h3"

            h4_count = len(soup.find_all("h4"))
            if h4_count > SPLIT_HEURISTIC_THRESHOLD: return "h4"
            return None
        except:
            return None

    def _regex_split(self, content: str, tag: str, file_stem: str, rel_path: str) -> List[Document]:
        """正则物理切割"""
        pattern = f"(<{tag}.*?>.*?</{tag}>)"
        chunks = re.split(pattern, content, flags=re.DOTALL | re.IGNORECASE)

        docs = []
        current_header = file_stem

        # 处理序言
        if chunks and chunks[0].strip():
            md = self._html_to_md(chunks[0])
            if len(md) > MIN_CONTENT_LENGTH:
                docs.append(Document(
                    page_content=md,
                    metadata={"source": file_stem, "title": f"{file_stem} (序言)", "full_path": rel_path, "is_chunk": True}
                ))

        for i in range(1, len(chunks), 2):
            header_html = chunks[i]
            body_html = chunks[i+1] if i+1 < len(chunks) else ""

            try:
                raw_title = re.sub(r"<[^>]+>", "", header_html).strip()
                current_header = raw_title if raw_title else current_header
            except:
                pass

            full_chunk_html = header_html + body_html
            md_text = self._html_to_md(full_chunk_html)

            if len(md_text) > MIN_CONTENT_LENGTH:
                docs.append(Document(
                    page_content=md_text,
                    metadata={
                        "source": file_stem,
                        "title": current_header,
                        "full_path": rel_path,
                        "is_chunk": True
                    }
                ))

        return docs

    def _html_to_md(self, html: str) -> str:
        try:
            return self.h2t.handle(html).strip()
        except:
            return ""

    def _read_file_encoded(self, path: Path) -> str:
        try:
            with open(path, "rb") as f:
                raw = f.read()
            if raw.startswith(b"\xef\xbb\xbf"): return raw.decode("utf-8-sig")
            for enc in ["utf-8", "gb18030", "gbk", "big5", "latin-1"]:
                try:
                    return raw.decode(enc)
                except:
                    continue
            return ""
        except:
            return ""

    def _save_and_index(self, documents: List[Document]):
        data_to_save = [{"page_content": d.page_content, "metadata": d.metadata} for d in documents]
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False)

        tokenized_corpus = [jieba.lcut(d.page_content) for d in documents]
        bm25 = BM25Okapi(tokenized_corpus)

        with open(self.index_dir / "documents.pkl", "wb") as f:
            pickle.dump(documents, f)

        with open(self.index_dir / "bm25_model.pkl", "wb") as f:
            pickle.dump(bm25, f)