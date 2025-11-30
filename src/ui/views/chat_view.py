import flet as ft
from src.services.session_manager import SessionManager
from src.services.config_manager import config_manager
from src.services.library_manager import library_manager
from src.core.llm import create_llm
from src.core.agent import DndAgentExecutor
from src.core.retriever import BM25Retriever


class ChatView(ft.Container):
    def __init__(self, page: ft.Page, session_manager: SessionManager):
        super().__init__(expand=True, padding=0)
        self.main_page = page
        self.sm = session_manager
        self.agent = None
        self.retriever = BM25Retriever()

        # UI
        self.history_list = ft.ListView(width=250, spacing=2, padding=10)
        self.chat_area = ft.ListView(expand=True, spacing=15, padding=20, auto_scroll=True)
        self.input_field = ft.TextField(hint_text="选择规则库以开始...", expand=True, border_radius=20,
                                        on_submit=self.send_message, disabled=True)

        # 稳健写法：Dropdown 初始化
        self.dd_library = ft.Dropdown(
            width=200,
            label="选择规则库",
            text_size=12,
            height=45
        )
        self.dd_library.content_padding = 5
        self.dd_library.on_change = self.on_lib_change

        self.init_ui()
        # 注意：不要在此处调用 load_libs()

    def did_mount(self):
        """生命周期：挂载后加载数据"""
        self.load_libs()

    def init_ui(self):
        sidebar = ft.Container(width=260, bgcolor=ft.colors.GREY_100, content=ft.Column([
            ft.Container(content=ft.Column([
                ft.ElevatedButton("新建会话", icon=ft.icons.ADD, on_click=self.create_new_session, width=200),
                ft.Container(height=10),
                self.dd_library
            ]), padding=10),
            ft.Divider(height=1),
            self.history_list
        ]))

        main_chat = ft.Column([
            self.chat_area,
            ft.Container(content=ft.Row([self.input_field, ft.IconButton(ft.icons.SEND, icon_color=ft.colors.BLUE,
                                                                         on_click=self.send_message)]), padding=10,
                         bgcolor=ft.colors.WHITE)
        ], expand=True)

        self.content = ft.Row([sidebar, ft.VerticalDivider(width=1), main_chat], spacing=0)

    def load_libs(self):
        libs = library_manager.get_libraries()
        self.dd_library.options = [ft.dropdown.Option(l['id'], l['title']) for l in libs]
        if libs:
            self.dd_library.value = libs[0]['id']
            # 安全触发
            self.on_lib_change(None)
        else:
            self.dd_library.hint_text = "请先去卷宗室导入数据"
        self.refresh_history()

    def on_lib_change(self, e):
        lid = self.dd_library.value
        path = library_manager.get_library_path(lid)
        if path:
            self.retriever.load_index(str(path))
            if self.agent: self.agent.retriever = self.retriever
            self.input_field.disabled = False
            self.input_field.hint_text = "输入你的问题..."
            self.main_page.snack_bar = ft.SnackBar(ft.Text(f"已加载: {self.dd_library.text}"))
            self.main_page.snack_bar.open = True
            self.update()

    def refresh_history(self):
        self.history_list.controls.clear()
        for s in self.sm.get_all_sessions():
            bg = ft.colors.BLUE_100 if s["id"] == self.sm.current_session_id else None
            self.history_list.controls.append(ft.Container(
                content=ft.Row([ft.Icon(ft.icons.CHAT_BUBBLE, size=16), ft.Text(s["title"], size=14, expand=True)]),
                padding=10, bgcolor=bg, border_radius=5, on_click=lambda e, sid=s["id"]: self.load_session(sid)
            ))
        self.update()

    def create_new_session(self, e):
        sid = self.sm.new_session()
        self.load_session(sid)

    def load_session(self, sid):
        self.sm.current_session_id = sid
        data = self.sm.load_session(sid)
        self.chat_area.controls.clear()
        for msg in data.get("history", []):
            self.render_bubble(msg["role"], msg["content"], msg.get("trace"))
        self.refresh_history()
        self.update()

    def render_bubble(self, role, content, trace=None):
        is_user = role == "user"
        align = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
        bg = ft.colors.BLUE_50 if is_user else ft.colors.WHITE

        ctrls = [ft.Markdown(content)]
        if trace and not is_user:
            t_txt = "\n\n".join([f"`{t['type']}` {t['content']}" for t in trace])
            ctrls.insert(0, ft.ExpansionTile(title=ft.Text("思维链", size=12), controls=[
                ft.Container(ft.Markdown(t_txt), bgcolor=ft.colors.GREY_50, padding=10)]))

        self.chat_area.controls.append(ft.Row([ft.Container(ft.Column(ctrls), bgcolor=bg, padding=15, border_radius=10,
                                                            width=600 if not is_user else None)], alignment=align))

    def send_message(self, e):
        txt = self.input_field.value
        if not txt: return
        if not self.sm.current_session_id: self.create_new_session(None)

        self.input_field.value = ""
        self.render_bubble("user", txt)
        self.sm.add_message(self.sm.current_session_id, "user", txt)
        self.update()
        self.main_page.run_task(self.process_ai, txt)

    async def process_ai(self, txt):
        if not self.agent:
            cfg = config_manager.load_settings()
            llm = create_llm(cfg['api_provider'], cfg['api_key'], cfg['model_name'], base_url=cfg['api_base_url'])
            self.agent = DndAgentExecutor(llm, self.retriever, cfg)
            self.agent.retriever = self.retriever  # Force update

        try:
            loader = ft.Text("Thinking...")
            self.chat_area.controls.append(loader)
            self.update()

            res = self.agent.invoke(txt)
            self.chat_area.controls.remove(loader)

            self.render_bubble("ai", res.answer, res.trace_log)
            self.sm.add_message(self.sm.current_session_id, "ai", res.answer, res.trace_log)
        except Exception as ex:
            self.render_bubble("ai", f"Error: {ex}")
        self.update()