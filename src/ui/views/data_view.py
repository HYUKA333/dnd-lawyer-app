import flet as ft
from src.services.chm_processor import CHMProcessor
from src.services.config_manager import config_manager


class DataView(ft.Container):
    def __init__(self):
        super().__init__(expand=True, padding=30)

        self.status_text = ft.Text("等待操作...", color=ft.colors.GREY)
        self.progress_bar = ft.ProgressBar(width=400, value=0, visible=False)
        self.log_view = ft.ListView(expand=True, height=200, bgcolor=ft.colors.GREY_50, padding=10)

        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)

        self.init_ui()

    def did_mount(self):
        self.page.overlay.append(self.file_picker)
        self.page.update()

    def init_ui(self):
        self.content = ft.Column([
            ft.Text("卷宗室 (Data Forge)", size=28, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("1. 请准备好 DND 规则文件的 .CHM 格式"),
            ft.Text("2. 确保 bin/7za.exe 文件存在 (用于解压)"),
            ft.Container(height=20),
            ft.ElevatedButton(
                "选择 CHM 文件并开始处理",
                icon=ft.icons.UPLOAD_FILE,
                height=50,
                on_click=lambda _: self.file_picker.pick_files(allow_multiple=False, allowed_extensions=["chm"])
            ),
            ft.Container(height=20),
            ft.Text("处理进度:", weight=ft.FontWeight.BOLD),
            self.progress_bar,
            self.status_text,
            ft.Container(height=10),
            ft.Text("系统日志:"),
            ft.Container(
                content=self.log_view,
                border=ft.border.all(1, ft.colors.GREY_300),
                border_radius=5,
                height=300
            )
        ])

    def on_file_picked(self, e: ft.FilePickerResultEvent):
        if e.files:
            file_path = e.files[0].path
            self.status_text.value = f"已选择: {file_path}"
            self.status_text.color = ft.colors.BLACK
            self.progress_bar.visible = True
            self.log_view.controls.clear()
            self.update()

            self.page.run_task(self.run_process, file_path)

    async def run_process(self, file_path):
        processor = CHMProcessor(file_path, str(config_manager.root_dir))

        def callback(progress, msg):
            self.progress_bar.value = progress
            self.status_text.value = msg
            self.log_view.controls.append(ft.Text(f"[{int(progress * 100)}%] {msg}", size=12))
            self.log_view.scroll_to(offset=-1, duration=100)  # Auto scroll to bottom
            self.update()

        try:
            # 注意: run_pipeline 是同步阻塞的，在 Flet 异步任务中调用最好用 run_in_executor
            # 这里简化直接调用，可能会卡顿 UI 一瞬间
            processor.run_pipeline(callback)
            self.status_text.value = "✅ 所有处理完成！现在可以开始对话了。"
            self.status_text.color = ft.colors.GREEN
        except Exception as e:
            self.status_text.value = f"❌ 失败: {str(e)}"
            self.status_text.color = ft.colors.RED
            self.log_view.controls.append(ft.Text(f"ERROR: {str(e)}", color=ft.colors.RED))

        self.update()