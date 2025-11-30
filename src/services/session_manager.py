"""
模块: Session Manager
对应规格书: src/services/session_manager.py
职责: 负责管理多轮对话。维护 session_id -> AgentInstance 映射(可选)，
      以及持久化对话记录到本地磁盘。
"""
import json
import os
import time
import uuid
from pathlib import Path
from typing import List, Dict, Optional


class SessionManager:
    def __init__(self, data_dir: str):
        self.sessions_dir = Path(data_dir) / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_session_id: Optional[str] = None

    def get_all_sessions(self) -> List[Dict]:
        """获取所有会话的元数据（按时间倒序）"""
        sessions = []
        for f in self.sessions_dir.glob("*.json"):
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    sessions.append({
                        "id": data["id"],
                        "title": data.get("title", "未命名会话"),
                        "updated_at": data.get("updated_at", 0)
                    })
            except Exception:
                continue

        return sorted(sessions, key=lambda x: x["updated_at"], reverse=True)

    def new_session(self) -> str:
        """创建一个新会话"""
        session_id = str(uuid.uuid4())
        timestamp = time.time()
        session_data = {
            "id": session_id,
            "title": f"新会话 {time.strftime('%H:%M', time.localtime(timestamp))}",
            "created_at": timestamp,
            "updated_at": timestamp,
            "history": []  # List of {role: str, content: str, trace: list}
        }
        self._save_file(session_id, session_data)
        self.current_session_id = session_id
        return session_id

    def load_session(self, session_id: str) -> Dict:
        """加载指定会话详情"""
        file_path = self.sessions_dir / f"{session_id}.json"
        if not file_path.exists():
            return {}

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.current_session_id = session_id
            return data

    def add_message(self, session_id: str, role: str, content: str, trace: list = None):
        """追加消息并保存"""
        data = self.load_session(session_id)
        if not data: return

        message = {
            "role": role,
            "content": content,
            "timestamp": time.time()
        }
        if trace:
            # 简化 Trace 对象为 dict 以便 JSON 序列化
            message["trace"] = [
                {"type": t.step_type, "content": t.content}
                for t in trace
            ]

        data["history"].append(message)
        data["updated_at"] = time.time()

        # 自动更新标题 (如果是第一条用户消息)
        if role == "user" and len(data["history"]) <= 2:
            data["title"] = content[:20].strip()

        self._save_file(session_id, data)

    def delete_session(self, session_id: str):
        file_path = self.sessions_dir / f"{session_id}.json"
        if file_path.exists():
            os.remove(file_path)
            if self.current_session_id == session_id:
                self.current_session_id = None

    def _save_file(self, session_id: str, data: Dict):
        file_path = self.sessions_dir / f"{session_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)