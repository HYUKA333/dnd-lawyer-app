import flet as ft
from src.services.session_manager import SessionManager
from src.services.config_manager import config_manager
from src.core.llm import create_llm
from src.core.agent import DndAgentExecutor
from src.core.retriever import BM25Retriever


class ChatView(ft.Container):
    def __init__(self, page: ft.Page, session_manager: SessionManager):
        super().__init__(expand=True, padding=0)
        self.page = page
        self.sm = session_manager

        # 核心对象
        self.agent = None
        self.retriever = BM25Retriever(str(config_manager.data_dir))

        # UI 组件
        self.history_list = ft.ListView(width=250, spacing=2, padding=10)
        self.chat_area = ft.ListView(expand=True, spacing=15, padding=20, auto_scroll=True)
        self.input_field = ft.TextField(
            hint_text="输入你的问题 (例如: 圣武士可以用投掷武器至圣斩吗?)...",
            expand=True,
            border_radius=20,
            on_submit=self.send_message
        )

        self.init_ui()
        self.refresh_history_sidebar()

    def init_ui(self):
        # 侧边栏: 历史会话
        sidebar = ft.Container(
            width=260,
            bgcolor=ft.colors.GREY_100,
            content=ft.Column([
                ft.Container(
                    content=ft.ElevatedButton("新建会话", icon=ft.icons.ADD, on_click=self.create_new_session,
                                              width=200),
                    padding=10
                ),
                ft.Divider(height=1),
                self.history_list
            ])
        )

        # 主聊天区
        main_chat = ft.Column([
            self.chat_area,
            ft.Container(
                content=ft.Row([
                    self.input_field,
                    ft.IconButton(icon=ft.icons.SEND, icon_color=ft.colors.BLUE, on_click=self.send_message)
                ]),
                padding=10,
                bgcolor=ft.colors.WHITE
            )
        ], expand=True)

        self.content = ft.Row([sidebar, ft.VerticalDivider(width=1), main_chat], spacing=0)

    def refresh_history_sidebar(self):
        self.history_list.controls.clear()
        sessions = self.sm.get_all_sessions()

        for s in sessions:
            is_active = s["id"] == self.sm.current_session_id
            self.history_list.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.CHAT_BUBBLE_OUTLINE, size=16),
                        ft.Text(s["title"], size=14, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                        ft.IconButton(
                            ft.icons.DELETE_OUTLINE,
                            size=16,
                            on_click=lambda e, sid=s["id"]: self.delete_session(sid)
                        )
                    ]),
                    padding=10,
                    border_radius=5,
                    bgcolor=ft.colors.BLUE_100 if is_active else None,
                    on_click=lambda e, sid=s["id"]: self.load_session_ui(sid),
                    ink=True
                )
            )
        self.page.update()

    def create_new_session(self, e):
        sid = self.sm.new_session()
        self.load_session_ui(sid)

    def delete_session(self, sid):
        self.sm.delete_session(sid)
        if self.sm.current_session_id == sid:
            self.chat_area.controls.clear()
        self.refresh_history_sidebar()

    def load_session_ui(self, sid):
        self.sm.current_session_id = sid
        data = self.sm.load_session(sid)
        self.chat_area.controls.clear()

        for msg in data.get("history", []):
            self.render_message_bubble(msg["role"], msg["content"], msg.get("trace"))

        self.refresh_history_sidebar()
        self.page.update()

    def render_message_bubble(self, role, content, trace=None):
        is_user = role == "user"
        align = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
        bg_color = ft.colors.BLUE_50 if is_user else ft.colors.WHITE

        content_ctrls = [ft.Markdown(content, selectable=True)]

        # 显示思维链 (如果存在)
        if trace and not is_user:
            trace_md = "\n\n".join([f"**`{t['type']}`** {t['content']}" for t in trace])
            expander = ft.ExpansionTile(
                title=ft.Text("思维链 (Thinking Process)", size=12, color=ft.colors.GREY),
                controls=[ft.Container(ft.Markdown(trace_md), padding=10, bgcolor=ft.colors.GREY_50)],
                initially_expanded=False
            )
            content_ctrls.insert(0, expander)

        bubble = ft.Container(
            content=ft.Column(content_ctrls),
            bgcolor=bg_color,
            padding=15,
            border_radius=10,
            border=ft.border.all(1, ft.colors.GREY_200) if not is_user else None,
            width=600 if not is_user else None,
            maw=800
        )

        self.chat_area.controls.append(ft.Row([bubble], alignment=align))

    def send_message(self, e):
        text = self.input_field.value
        if not text: return

        if not self.sm.current_session_id:
            self.create_new_session(None)

        self.input_field.value = ""
        self.render_message_bubble("user", text)
        self.sm.add_message(self.sm.current_session_id, "user", text)
        self.page.update()

        # 异步处理 (UI 不卡死)
        self.page.run_task(self.process_ai_response, text)

    async def process_ai_response(self, text):
        # 初始化 Agent
        if not self.agent:
            try:
                settings = config_manager.load_settings()
                llm = create_llm(
                    provider=settings['api_provider'],
                    api_key=settings['api_key'],
                    model_name=settings['model_name'],
                    base_url=settings['api_base_url']
                )
                self.agent = DndAgentExecutor(llm, self.retriever, settings)
            except Exception as e:
                self.render_message_bubble("ai", f"❌ 初始化失败: {str(e)}\n请先检查设置页面的 API 配置。")
                self.page.update()
                return

        try:
            # 显示 "正在思考..."
            loading = ft.Text("Thinking...", italic=True, color=ft.colors.GREY)
            self.chat_area.controls.append(loading)
            self.page.update()

            # 执行
            # 注意: agent.py 中的 invoke 是同步的，如果需要不阻塞UI，建议在 agent中实现 async invoke
            # 这里简单处理，直接调用
            result = self.agent.invoke(text)

            # 移除 loading
            self.chat_area.controls.remove(loading)

            # 显示结果
            self.render_message_bubble("ai", result.answer, result.trace_log)
            self.sm.add_message(self.sm.current_session_id, "ai", result.answer, result.trace_log)
            self.refresh_history_sidebar()  # 更新标题

        except Exception as e:
            self.render_message_bubble("ai", f"❌ 运行时错误: {str(e)}")

        self.page.update()