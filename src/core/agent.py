"""
模块: Agent Logic
基于原 agent.py (v2.8) 改造，移除全局配置依赖，改为 __init__ 传参。
"""

import re
import time
from typing import List, Dict, Any, Tuple, NamedTuple, Set
from dataclasses import dataclass, field, asdict

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseLanguageModel


# === Data Structures ===

@dataclass
class AgentStep:
    step_type: str
    step_name: str
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class DocSnapshot:
    id: int
    path: str
    snippet: str
    source: str


@dataclass
class AgentResult:
    answer: str
    final_pool: List[DocSnapshot]
    trace_log: List[AgentStep]
    history_cleaned: bool = True


# === Prompts (Kept same as updated logic) ===
# 为了节省空间，此处简略引用，实际代码中包含完整的 prompt 内容

PROMPT_QUERY = ChatPromptTemplate.from_messages([
    ("system", """你是一个DND规则检索专家。你的任务是为搜索引擎生成一个精准的关键词。
请直接提取用于检索DND规则库的**最核心关键词**。
不要包含"搜索"、"查找"等指令词，只返回内容关键词。
请严格按照格式输出:
首要查询: <你的关键词>"""),
    ("human", """[对话历史]
{history}

[当前用户问题]
{input}""")
])

PROMPT_BLACKLIST = ChatPromptTemplate.from_messages([
    ("system", """你是一个DND规则审核员。找出当前文档列表中与用户问题无关的文档。
请严格按照格式输出:
拉黑ID: <id1, id2...> (如果没有，留空)"""),
    ("human", """[用户问题]
{input}

[待审核文档列表 (带ID)]
{context}""")
])

PROMPT_EVALUATE = ChatPromptTemplate.from_messages([
    ("system", """你是一个DND规则向导。判断是否需要继续搜索。
决策: <STOP 或 NEXT>
[如果 NEXT]
新查询词: <keyword>"""),
    ("human", """[用户问题]
{input}

[当前清洗后的文档池]
{context}""")
])

PROMPT_COT3 = ChatPromptTemplate.from_messages([
    ("system", """你是一个DND规则专家。基于提供的规则文档回答用户问题。
1. **引用明确**: 必须基于 Context 回答。
2. **诚实**: 如果 Context 里没有答案，请直接说未找到。"""),
    ("human", """[对话历史]
{history}

[用户问题]
{input}

[规则文档 (Context)]
{context}
""")
])


class EvaluateDecision(NamedTuple):
    action: str
    next_query: str


class AgentHelpers:
    @staticmethod
    def format_docs_for_prompt(docs: List[Document]) -> Tuple[str, Dict[int, str]]:
        if not docs:
            return "当前文档池为空。", {}
        formatted = []
        id_map = {}
        for i, doc in enumerate(docs):
            full_path = doc.metadata.get('full_path', 'Unknown')
            preview = doc.page_content[:250].replace('\n', ' ')
            formatted.append(f"[ID: {i}] 路径: {full_path}\n      内容: {preview}...")
            id_map[i] = full_path
        return "\n".join(formatted), id_map

    @staticmethod
    def update_doc_pool(current_pool: List[Document], new_docs: List[Document], limit: int) -> List[Document]:
        pool_map = {d.metadata.get('full_path'): d for d in current_pool}
        for doc in new_docs:
            p = doc.metadata.get('full_path')
            if p:
                if p in pool_map:
                    del pool_map[p]
                pool_map[p] = doc
        all_docs = list(pool_map.values())
        if len(all_docs) > limit:
            return all_docs[-limit:]
        return all_docs

    @staticmethod
    def parse_query(text: str) -> str:
        match = re.search(r"首要查询:\s*(.*)", text, re.DOTALL)
        return match.group(1).strip() if match else text.strip()

    @staticmethod
    def parse_blacklist(text: str) -> List[int]:
        ids = []
        match = re.search(r"拉黑ID:\s*(.*)", text, re.DOTALL)
        if match:
            content = match.group(1).strip()
            if "无" in content or not content:
                return []
            content = content.replace("，", ",")
            parts = content.split(",")
            for p in parts:
                try:
                    ids.append(int(p.strip()))
                except:
                    pass
        return ids

    @staticmethod
    def parse_evaluate(text: str) -> EvaluateDecision:
        action = "STOP"
        next_q = ""
        dec_match = re.search(r"决策:\s*(STOP|NEXT)", text, re.IGNORECASE)
        if dec_match:
            action = dec_match.group(1).upper()
        if action == "NEXT":
            q_match = re.search(r"新查询词:\s*(.*)", text)
            if q_match:
                next_q = q_match.group(1).strip()
        return EvaluateDecision(action, next_q)

    @staticmethod
    def parse_final_answer(text: str) -> str:
        match = re.search(r"回答:\s*(.*)", text, re.DOTALL)
        return match.group(1).strip() if match else text.strip()


class DndAgentExecutor:
    def __init__(self, llm: BaseLanguageModel, retriever, settings: Dict[str, Any] = None):
        self.llm = llm
        self.retriever = retriever
        # 配置参数注入
        self.settings = settings or {}
        self.doc_pool_limit = 8
        self.max_loops = 2

        # Memory
        self.chat_history: List[Tuple[str, str]] = []
        self.doc_pool: List[Document] = []

        # Chains
        self.chain_query = PROMPT_QUERY | self.llm | StrOutputParser()
        self.chain_blacklist = PROMPT_BLACKLIST | self.llm | StrOutputParser()
        self.chain_evaluate = PROMPT_EVALUATE | self.llm | StrOutputParser()
        self.chain_final = PROMPT_COT3 | self.llm | StrOutputParser()

    def load_history_str(self) -> str:
        if not self.chat_history:
            return "无"
        lines = []
        for h, a in self.chat_history:
            lines.append(f"User: {h}")
            lines.append(f"AI: {a}")
        return "\n".join(lines)

    def invoke(self, user_input: str) -> AgentResult:
        trace = []
        history_str = self.load_history_str()
        blacklist_session: Set[str] = set()

        # 1. Initial Query
        next_query = user_input
        # 简单判断，如果太短可能就是关键词
        if len(user_input) > 30:
            raw_q = self.chain_query.invoke({"history": history_str, "input": user_input})
            next_query = AgentHelpers.parse_query(raw_q)
            trace.append(AgentStep("Think", "Initial Query", f"提炼关键词: {next_query}"))
        else:
            trace.append(AgentStep("Think", "Initial Query", "输入简短，直接作为查询词"))

        # 2. Loop
        loop_count = 0
        while loop_count < self.max_loops:
            loop_count += 1
            trace.append(AgentStep("Loop", f"Round {loop_count}", f"开始检索: {next_query}"))

            # Search
            top_k = self.settings.get("top_k", 10)
            new_docs = self.retriever.search(
                query=next_query,
                blacklist_paths=list(blacklist_session),
                top_k=top_k
            )

            # Update Pool
            prev_len = len(self.doc_pool)
            self.doc_pool = AgentHelpers.update_doc_pool(self.doc_pool, new_docs, limit=self.doc_pool_limit)
            trace.append(AgentStep("System", "Pool Update", f"Docs: {prev_len} -> {len(self.doc_pool)}"))

            # Blacklist Check
            ctx_str, id_map = AgentHelpers.format_docs_for_prompt(self.doc_pool)
            if self.doc_pool:
                bl_raw = self.chain_blacklist.invoke({"input": user_input, "context": ctx_str})
                bad_ids = AgentHelpers.parse_blacklist(bl_raw)
                if bad_ids:
                    removed_paths = []
                    for bid in bad_ids:
                        if bid in id_map:
                            path = id_map[bid]
                            if path not in blacklist_session:
                                blacklist_session.add(path)
                                removed_paths.append(path)

                    if removed_paths:
                        self.doc_pool = [d for d in self.doc_pool if
                                         d.metadata.get('full_path') not in blacklist_session]
                        trace.append(AgentStep("Action", "Blacklist", f"拉黑 {len(removed_paths)} 个文档"))

            # Evaluate
            clean_ctx_str, _ = AgentHelpers.format_docs_for_prompt(self.doc_pool)
            eval_raw = self.chain_evaluate.invoke({"input": user_input, "context": clean_ctx_str})
            decision = AgentHelpers.parse_evaluate(eval_raw)
            trace.append(AgentStep("Decision", "Evaluation", f"{decision.action} | {decision.next_query}"))

            if decision.action == "STOP":
                break
            elif decision.action == "NEXT":
                if not decision.next_query or decision.next_query == next_query:
                    break
                next_query = decision.next_query

        # 3. Final
        trace.append(AgentStep("Think", "Final Generate", "生成最终回答"))
        final_ctx, _ = AgentHelpers.format_docs_for_prompt(self.doc_pool)

        cot3_raw = self.chain_final.invoke({
            "history": history_str,
            "input": user_input,
            "context": final_ctx
        })
        final_answer = AgentHelpers.parse_final_answer(cot3_raw)

        # Save history
        self.chat_history.append((user_input, final_answer))
        if len(self.chat_history) > 5:
            self.chat_history = self.chat_history[-5:]

        final_snapshots = [
            DocSnapshot(id=i, path=d.metadata.get('full_path', ''), snippet=d.page_content[:100],
                        source=d.metadata.get('source_title', ''))
            for i, d in enumerate(self.doc_pool)
        ]

        return AgentResult(answer=final_answer, final_pool=final_snapshots, trace_log=trace)