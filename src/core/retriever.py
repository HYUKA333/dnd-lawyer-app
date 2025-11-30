import os
import pickle
import jieba
import numpy as np
from typing import List, Optional
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

class BM25Retriever:
    def __init__(self, lib_path: str = None):
        self.bm25_model: Optional[BM25Okapi] = None
        self.documents: List[Document] = []
        self.loaded = False
        self.current_lib_path = lib_path

        if lib_path:
            self.load_index(lib_path)

    def load_index(self, lib_path: str):
        """热加载指定库的索引"""
        self.current_lib_path = lib_path
        index_dir = os.path.join(lib_path, "vector_store")
        model_path = os.path.join(index_dir, "bm25_model.pkl")
        docs_path = os.path.join(index_dir, "documents.pkl")

        if not os.path.exists(model_path):
            print(f"Index not found: {index_dir}")
            self.loaded = False
            return

        # 尝试加载项目根目录下的自定义词典
        root_dict = os.path.join("data", "dnd_terms.txt")
        if os.path.exists(root_dict):
            jieba.load_userdict(root_dict)

        try:
            with open(docs_path, 'rb') as f:
                self.documents = pickle.load(f)

            with open(model_path, 'rb') as f:
                self.bm25_model = pickle.load(f)

            self.loaded = True
        except Exception as e:
            print(f"Error loading index: {e}")
            self.loaded = False

    def search(self, query: str, top_k: int = 10, blacklist_paths: List[str] = None) -> List[Document]:
        if not self.loaded: return []
        if blacklist_paths is None: blacklist_paths = []

        tokenized_query = jieba.lcut(query)
        scores = self.bm25_model.get_scores(tokenized_query)

        # 优化策略：取 Top 5N 候选再过滤
        limit = min(max(top_k * 5, 50), len(self.documents))
        # argsort 返回从小到大的索引，取最后 limit 个并反转
        candidate_indices = np.argsort(scores)[-limit:][::-1]

        results = []
        for idx in candidate_indices:
            if scores[idx] <= 0: break # 无相关性

            doc = self.documents[idx]
            path = doc.metadata.get('full_path', '')

            if path in blacklist_paths: continue

            results.append(doc)
            if len(results) >= top_k: break

        return results