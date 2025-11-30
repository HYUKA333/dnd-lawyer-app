"""
模块: CHM Processor
对应规格书: src/services/chm_processor.py
"""
import os
import json
import pickle
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional
import jieba
from bs4 import BeautifulSoup
import html2text
from rank_bm25 import BM25Okapi
from langchain_core.documents import Document


class CHMProcessor:
    def __init__(self, chm_path: str, work_dir: str):
        self.chm_path = Path(chm_path)
        self.work_dir = Path(work_dir)
        self.source_dir = self.work_dir / "chm_source"
        self.data_dir = self.work_dir / "data"
        self.index_dir = self.data_dir / "vector_store"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def run_pipeline(self, progress_callback: Callable[[float, str], None]):
        """执行完整流程：解压 -> 分析 -> 清洗 -> 索引"""
        try:
            progress_callback(0.05, "正在解压 CHM 文件...")
            self._extract_chm()

            progress_callback(0.25, "正在分析 CHM 结构...")
            # 简化版分析，实际可集成 analyze_chm.py

            progress_callback(0.35, "正在清洗数据...")
            documents = self._process_data(progress_callback)

            progress_callback(0.75, "正在构建搜索索引...")
            self._build_index(documents)

            progress_callback(1.0, "索引构建完成！")

        except Exception as e:
            progress_callback(0.0, f"错误: {str(e)}")
            raise e

    def _extract_chm(self):
        bin_7z = Path(os.getcwd()) / "bin" / "7za.exe"
        if not bin_7z.exists():
            bin_7z = "7z"

        if self.source_dir.exists():
            shutil.rmtree(self.source_dir)
        self.source_dir.mkdir(parents=True, exist_ok=True)

        # -y: yes to all, -o: output dir
        cmd = [str(bin_7z), "x", str(self.chm_path), f"-o{self.source_dir}", "-y"]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    def _process_data(self, callback):
        documents = []
        html_files = list(self.source_dir.rglob("*.htm*"))
        total = len(html_files)

        for i, f in enumerate(html_files):
            if i % 10 == 0 and total > 0:
                percent = 0.35 + (i / total) * 0.4
                callback(percent, f"正在处理: {f.name}")

            try:
                # 兼容编码读取
                content_str = ""
                with open(f, 'rb') as fb:
                    raw = fb.read()
                    for enc in ['utf-8', 'gbk', 'gb18030', 'latin-1']:
                        try:
                            content_str = raw.decode(enc)
                            break
                        except:
                            continue

                if not content_str: continue

                soup = BeautifulSoup(content_str, 'html.parser')
                text = html2text.html2text(str(soup))

                if len(text.strip()) > 50:
                    rel_path = f.relative_to(self.source_dir).as_posix()
                    documents.append(Document(
                        page_content=text,
                        metadata={
                            "full_path": rel_path,
                            "source_title": f.stem
                        }
                    ))
            except Exception as e:
                print(f"Skipped {f}: {e}")

        # 保存 rules_data.json
        json_path = self.data_dir / "rules_data.json"
        data_to_save = [{"page_content": d.page_content, "metadata": d.metadata} for d in documents]
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False)

        return documents

    def _build_index(self, documents: list[Document]):
        # 构建 Jieba + BM25
        tokenized_corpus = []
        for doc in documents:
            tokens = jieba.lcut(doc.page_content)
            tokenized_corpus.append(tokens)

        bm25 = BM25Okapi(tokenized_corpus)

        with open(self.index_dir / "documents.pkl", "wb") as f:
            pickle.dump(documents, f)

        with open(self.index_dir / "bm25_model.pkl", "wb") as f:
            pickle.dump(bm25, f)