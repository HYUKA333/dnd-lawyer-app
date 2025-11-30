import flet as ft
from src.services.chm_processor import CHMProcessor
import os


class DataView(ft.UserControl):
    # 修复：移除 page 参数，避免 "missing 1 required positional argument" 错误
    def __init__(self):
        super().__init__()
        # 注意：此时 self.page 还是 None，不能在这里使用它
        self.processor = CHMProcessor()
        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)
        self.status_text = ft.Text("", size=12, color=ft.colors.GREY)
        self.rules_list = ft.Column(scroll=ft.ScrollMode.AUTO)

    def did_mount(self):
        """
        生命周期钩子：当控件被添加到页面后触发。
        此时 self.page 已经由 Flet 框架自动赋值。
        """
        # 必须将 file_picker 添加到 page.overlay 才能弹出文件选择框
        if self.page and self.file_picker not in self.page.overlay:
            self.page.overlay.append(self.file_picker)
            self.page.update()

        # 加载已有规则
        self.refresh_rules_list()

    def build(self):
        return ft.Container(
            padding=20,
            expand=True,
            content=ft.Column(
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("卷宗室 (Rule Books)", style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                            ft.ElevatedButton(
                                "新建规则",
                                icon=ft.icons.ADD,
                                # 点击触发文件选择
                                on_click=lambda _: self.file_picker.pick_files(
                                    allow_multiple=False,
                                    allowed_extensions=["chm"]
                                )
                            )
                        ]
                    ),
                    ft.Divider(),
                    self.status_text,
                    ft.Container(
                        expand=True,
                        content=self.rules_list
                    )
                ]
            )
        )

    def on_file_picked(self, e: ft.FilePickerResultEvent):
        """处理文件选择回调"""
        if not e.files:
            return

        file_path = e.files[0].path
        self.status_text.value = f"正在处理文件: {os.path.basename(file_path)}... (请查看控制台日志)"
        self.status_text.color = ft.colors.BLUE
        self.status_text.update()

        # 异步调用处理器
        try:
            success = self.processor.process_chm(file_path)
            if success:
                self.status_text.value = f"成功导入: {os.path.basename(file_path)}"
                self.status_text.color = ft.colors.GREEN
                self.refresh_rules_list()
            else:
                self.status_text.value = "导入失败，请检查 bin 目录下的 7za.exe 是否可用，或查看控制台报错。"
                self.status_text.color = ft.colors.RED
        except Exception as ex:
            self.status_text.value = f"发生错误: {str(ex)}"
            self.status_text.color = ft.colors.RED

        self.status_text.update()

    def refresh_rules_list(self):
        """刷新列表显示"""
        self.rules_list.controls.clear()

        data_file = os.path.join(self.processor.output_dir, "knowledge_base.jsonl")

        if os.path.exists(data_file):
            try:
                size_mb = os.path.getsize(data_file) / (1024 * 1024)
                count = 0
                with open(data_file, 'r', encoding='utf-8') as f:
                    for _ in f: count += 1

                self.rules_list.controls.append(
                    ft.ListTile(
                        leading=ft.Icon(ft.icons.LIBRARY_BOOKS, color=ft.colors.AMBER),
                        title=ft.Text("Knowledge Base Main"),
                        subtitle=ft.Text(f"包含 {count} 条规则片段 | 文件大小: {size_mb:.2f} MB"),
                    )
                )
            except Exception:
                self.rules_list.controls.append(ft.Text("无法读取规则数据库"))
        else:
            self.rules_list.controls.append(
                ft.Container(
                    content=ft.Text("暂无数据，请点击右上角导入 CHM 规则书", color=ft.colors.GREY_500),
                    padding=20,
                    alignment=ft.alignment.center
                )
            )

        self.rules_list.update()