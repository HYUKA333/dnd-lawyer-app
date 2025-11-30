"""
模块: Retriever (BM25)
基于原 retriever.py 改造，改为类实例模式，支持动态重新加载。
"""
import os
import pickle
import jieba
import numpy as np
from typing import List
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi


class BM25Retriever:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.index_dir = os.path.join(data_dir, "vector_store")

        self.bm25_model_path = os.path.join(self.index_dir, "bm25_model.pkl")
        self.documents_path = os.path.join(self.index_dir, "documents.pkl")

        self.bm25_model: BM25Okapi = None
        self.documents: List[Document] = []
        self.loaded = False

    def load_index(self):
        """加载磁盘上的索引文件"""
        if not os.path.exists(self.bm25_model_path) or not os.path.exists(self.documents_path):
            raise FileNotFoundError("Index files not found. Please build index first.")

        # 加载自定义词典（如果有）
        dict_path = os.path.join(self.data_dir, "dnd_terms.txt")
        if os.path.exists(dict_path):
            jieba.load_userdict(dict_path)

        with open(self.documents_path, 'rb') as f:
            self.documents = pickle.load(f)

        with open(self.bm25_model_path, 'rb') as f:
            self.bm25_model = pickle.load(f)

        self.loaded = True

    def search(self, query: str, top_k: int = 10, blacklist_paths: List[str] = None) -> List[Document]:
        if not self.loaded:
            self.load_index()

        if blacklist_paths is None:
            blacklist_paths = []

        # 1. 分词
        tokenized_query = jieba.lcut(query)

        # 2. 打分
        scores = self.bm25_model.get_scores(tokenized_query)

        # 3. 排序
        # 简单的优化：只取前 top_k * 5 个候选，然后过滤
        candidate_limit = min(max(top_k * 5, 50), len(self.documents))
        candidate_indices = np.argsort(scores)[-candidate_limit:][::-1]

        results = []
        for idx in candidate_indices:
            if scores[idx] <= 0.0:
                break

            doc = self.documents[idx]
            path = doc.metadata.get('full_path', '')

            # 黑名单过滤
            if path in blacklist_paths:
                continue

            results.append(doc)
            if len(results) >= top_k:
                break

        return results