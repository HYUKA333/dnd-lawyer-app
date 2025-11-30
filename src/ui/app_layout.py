import flet as ft
from src.ui.views.chat_view import ChatView
from src.ui.views.data_view import DataView
from src.ui.views.setup_view import SetupView
from src.services.session_manager import SessionManager
from src.services.config_manager import config_manager


class AppLayout(ft.Row):
    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=0)
        self.page = page
        self.session_manager = SessionManager(str(config_manager.data_dir))

        # 初始化 Views
        self.view_chat = ChatView(page, self.session_manager)
        self.view_data = DataView()
        self.view_setup = SetupView()

        # 侧边导航栏
        self.rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=200,
            group_alignment=-0.9,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.icons.GAVEL_OUTLINED,
                    selected_icon=ft.icons.GAVEL,
                    label="法庭"
                ),
                ft.NavigationRailDestination(
                    icon=ft.icons.ARCHIVE_OUTLINED,
                    selected_icon=ft.icons.ARCHIVE,
                    label="卷宗室"
                ),
                ft.NavigationRailDestination(
                    icon=ft.icons.SETTINGS_OUTLINED,
                    selected_icon=ft.icons.SETTINGS,
                    label="事务所"
                ),
            ],
            on_change=self.on_nav_change,
        )

        # 内容区域
        self.content_area = ft.Container(expand=True, content=self.view_chat)

        self.controls = [
            self.rail,
            ft.VerticalDivider(width=1),
            self.content_area
        ]

    def on_nav_change(self, e):
        index = e.control.selected_index
        if index == 0:
            self.content_area.content = self.view_chat
        elif index == 1:
            self.content_area.content = self.view_data
        elif index == 2:
            self.content_area.content = self.view_setup

        self.content_area.update()