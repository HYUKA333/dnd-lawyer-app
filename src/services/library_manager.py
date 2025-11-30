import json
import shutil
import time
import uuid
import os
from pathlib import Path
from typing import List, Dict, Optional


class LibraryManager:
    """
    负责管理多个规则数据库 (Libraries)
    路径结构:
    data/libraries/
      ├── {lib_id}/
      │    ├── metadata.json
      │    ├── rules_data.json  <-- 原始内容 (用于查看)
      │    └── vector_store/    <-- 索引 (用于检索)
    """

    def __init__(self, data_root: str = "data"):
        self.root = Path(data_root)
        self.libs_dir = self.root / "libraries"
        self.libs_dir.mkdir(parents=True, exist_ok=True)

    def get_libraries(self) -> List[Dict]:
        """获取所有可用规则库的元数据"""
        libs = []
        for d in self.libs_dir.iterdir():
            if d.is_dir():
                meta_path = d / "metadata.json"
                if meta_path.exists():
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            libs.append(json.load(f))
                    except Exception:
                        continue
        return sorted(libs, key=lambda x: x.get("created_at", 0), reverse=True)

    def create_library(self, title: str, description: str = "") -> str:
        """创建新库"""
        lib_id = str(uuid.uuid4())[:8]
        lib_path = self.libs_dir / lib_id
        lib_path.mkdir(parents=True, exist_ok=True)
        (lib_path / "vector_store").mkdir()

        metadata = {
            "id": lib_id,
            "title": title,
            "description": description,
            "created_at": time.time(),
            "doc_count": 0,
            "path": str(lib_path.absolute())
        }
        self._save_meta(lib_id, metadata)
        return lib_id

    def delete_library(self, lib_id: str):
        """物理删除库"""
        lib_path = self.libs_dir / lib_id
        if lib_path.exists():
            shutil.rmtree(lib_path)

    def get_library_path(self, lib_id: str) -> Optional[Path]:
        path = self.libs_dir / lib_id
        return path if path.exists() else None

    def update_metadata(self, lib_id: str, **kwargs):
        lib_path = self.libs_dir / lib_id
        meta_path = lib_path / "metadata.json"
        if meta_path.exists():
            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data.update(kwargs)
            self._save_meta(lib_id, data)

    def _save_meta(self, lib_id: str, data: Dict):
        lib_path = self.libs_dir / lib_id
        with open(lib_path / "metadata.json", "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_rules_data(self, lib_id: str, limit: int = 100) -> List[Dict]:
        """
        读取 rules_data.json 的前 N 条数据用于预览
        """
        json_path = self.libs_dir / lib_id / "rules_data.json"
        if not json_path.exists():
            return []

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data[:limit]  # 只返回前N条防止卡顿
        except Exception:
            return []


# 全局单例
library_manager = LibraryManager()