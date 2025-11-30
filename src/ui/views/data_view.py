import flet as ft
import time
from src.services.library_manager import library_manager
from src.services.chm_processor import CHMProcessor


class DataView(ft.Container):
    def __init__(self):
        super().__init__(expand=True, padding=20)

        self.current_processor: CHMProcessor = None
        self.top_levels: list[str] = []
        self.new_lib_id: str = None
        self.viewing_lib_id: str = None

        # --- UI Components ---

        self.lib_list_view = ft.ListView(expand=True, spacing=10)
        self.btn_create_lib = ft.ElevatedButton("新建规则库", icon=ft.icons.ADD, on_click=self.show_create_view)

        # Wizard
        self.wizard_container = ft.Column(visible=False, expand=True, scroll=ft.ScrollMode.AUTO)
        self.tf_lib_name = ft.TextField(label="名称", width=400)
        self.tf_lib_desc = ft.TextField(label="描述", width=400)

        # FilePicker 初始化
        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)

        self.btn_upload = ft.ElevatedButton("选择 .CHM", icon=ft.icons.UPLOAD_FILE,
                                            on_click=lambda _: self.file_picker.pick_files(allow_multiple=False,
                                                                                           allowed_extensions=["chm"]))
        self.txt_file_status = ft.Text("未选择", color=ft.colors.GREY)
        self.folder_checkboxes = ft.Column()
        self.btn_process = ft.ElevatedButton("开始处理", icon=ft.icons.BUILD, on_click=self.start_processing,
                                             disabled=True)
        self.progress_bar = ft.ProgressBar(width=400, value=0, visible=False)
        self.status_text = ft.Text("")

        # --- 修复点：ListView 不接受 bgcolor 和 height，这些由外层 Container 控制 ---
        self.log_view = ft.ListView(auto_scroll=True, spacing=2)

        # Viewer
        self.viewer_container = ft.Column(visible=False, expand=True)
        self.viewer_list = ft.ListView(expand=True, spacing=5)
        self.viewer_title = ft.Text("数据库内容预览", size=20, weight=ft.FontWeight.BOLD)

        self.init_ui()

    def did_mount(self):
        if self.page and self.file_picker not in self.page.overlay:
            self.page.overlay.append(self.file_picker)
            self.page.update()

        self.refresh_lib_list()

    def will_unmount(self):
        if self.page and self.file_picker in self.page.overlay:
            self.page.overlay.remove(self.file_picker)
            self.page.update()

    def init_ui(self):
        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(text="库管理", content=self._build_manager_tab()),
                ft.Tab(text="新建向导", content=self.wizard_container),
                ft.Tab(text="内容浏览", content=self.viewer_container),
            ],
            expand=True,
            on_change=self.on_tab_change
        )
        self.content = self.tabs

    def _build_manager_tab(self):
        return ft.Column([
            ft.Row([ft.Text("规则库列表", size=24, weight=ft.FontWeight.BOLD), self.btn_create_lib],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(),
            self.lib_list_view
        ], expand=True)

    def on_tab_change(self, e):
        pass

    # --- Manager Logic ---
    def refresh_lib_list(self):
        self.lib_list_view.controls.clear()
        libs = library_manager.get_libraries()
        if not libs:
            self.lib_list_view.controls.append(ft.Text("暂无规则库"))

        for lib in libs:
            self.lib_list_view.controls.append(self._create_lib_card(lib))
        self.update()

    def _create_lib_card(self, lib):
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(lib['title'], size=18, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.IconButton(ft.icons.VISIBILITY, tooltip="浏览内容", icon_color=ft.colors.BLUE,
                                  on_click=lambda e, lid=lib['id']: self.show_viewer(lid)),
                    ft.IconButton(ft.icons.DELETE, tooltip="删除", icon_color=ft.colors.RED,
                                  on_click=lambda e, lid=lib['id']: self.delete_lib(lid)),
                ]),
                ft.Text(f"文档数: {lib.get('doc_count', 0)} | {lib['description']}", size=12, color=ft.colors.GREY),
            ]),
            padding=15, border=ft.border.all(1, ft.colors.GREY_300), border_radius=8, bgcolor=ft.colors.GREY_50
        )

    def delete_lib(self, lib_id):
        library_manager.delete_library(lib_id)
        self.refresh_lib_list()

    # --- Viewer Logic ---
    def show_viewer(self, lib_id):
        self.viewing_lib_id = lib_id
        self.viewer_list.controls.clear()

        data = library_manager.load_rules_data(lib_id, limit=100)
        self.viewer_title.value = f"预览: {lib_id} (前 {len(data)} 条)"

        for item in data:
            meta = item.get("metadata", {})
            content_preview = item.get("page_content", "")[:100].replace("\n", " ")

            self.viewer_list.controls.append(ft.Container(
                content=ft.Column([
                    ft.Text(f"标题: {meta.get('title', '无')}", weight=ft.FontWeight.BOLD),
                    ft.Text(f"来源: {meta.get('full_path', '未知')}", size=12, color=ft.colors.GREY),
                    ft.Text(content_preview + "...", size=12, italic=True)
                ]),
                padding=10, border=ft.border.all(1, ft.colors.GREY_200), border_radius=5
            ))

        self.tabs.selected_index = 2
        self.viewer_container.visible = True
        self.update()

    # --- Wizard Logic ---
    def show_create_view(self, e):
        self.tabs.selected_index = 1
        self.wizard_container.visible = True
        self.reset_wizard()
        self.update()

    def reset_wizard(self):
        self.tf_lib_name.value = ""
        self.tf_lib_desc.value = ""
        self.txt_file_status.value = "未选择"
        self.folder_checkboxes.controls.clear()
        self.log_view.controls.clear()
        self.btn_process.disabled = True

    def on_file_picked(self, e):
        if not e.files: return
        path = e.files[0].path
        self.txt_file_status.value = path
        if not self.tf_lib_name.value: self.tf_lib_name.value = e.files[0].name
        self.update()

        self.log_view.controls.append(ft.Text("正在分析结构..."))
        self.page.run_task(self.analyze_task, path)

    async def analyze_task(self, path):
        try:
            self.new_lib_id = library_manager.create_library(self.tf_lib_name.value, self.tf_lib_desc.value)
            self.current_processor = CHMProcessor(path, self.new_lib_id)

            self.current_processor.extract_chm(lambda p, m: None)
            top_levels = self.current_processor.analyze_top_levels()

            self.folder_checkboxes.controls.clear()
            for f in top_levels:
                cb = ft.Checkbox(label=f, value=True)
                self.folder_checkboxes.controls.append(cb)

            self.btn_process.disabled = False
            self.log_view.controls.append(ft.Text(f"发现 {len(top_levels)} 个目录", color=ft.colors.GREEN))
        except Exception as e:
            self.log_view.controls.append(ft.Text(f"错误: {e}", color=ft.colors.RED))
        self.update()

    def start_processing(self, e):
        selected = [cb.label for cb in self.folder_checkboxes.controls if cb.value]
        if not selected: return
        self.progress_bar.visible = True
        self.btn_process.disabled = True
        self.page.run_task(self.process_task, selected)

    async def process_task(self, selected):
        library_manager.update_metadata(self.new_lib_id, title=self.tf_lib_name.value,
                                        description=self.tf_lib_desc.value)

        def cb(p, m):
            self.progress_bar.value = p
            self.status_text.value = m
            self.log_view.controls.append(ft.Text(m, size=12, color=ft.colors.WHITE))
            self.log_view.scroll_to(offset=-1, duration=50)
            self.update()

        try:
            # 运行在后台任务
            self.current_processor.run_processing(selected, cb)
            self.status_text.value = "完成"
            time.sleep(1)
            self.tabs.selected_index = 0
            self.refresh_lib_list()
        except Exception as e:
            self.status_text.value = f"Error: {e}"
            self.log_view.controls.append(ft.Text(f"CRITICAL ERROR: {e}", color=ft.colors.RED))
        self.update()