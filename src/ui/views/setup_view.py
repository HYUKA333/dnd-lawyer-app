import flet as ft
from src.services.config_manager import config_manager


class SetupView(ft.Container):
    def __init__(self):
        super().__init__(expand=True, padding=30)

        # 控件
        self.api_provider = ft.Dropdown(
            label="API 提供商",
            options=[
                ft.dropdown.Option("openai", "OpenAI 兼容 (推荐)"),
                ft.dropdown.Option("google", "Google Gemini 官方"),
            ],
            value="openai",
            width=400
        )
        self.api_key = ft.TextField(label="API Key", password=True, can_reveal_password=True, width=400)
        self.base_url = ft.TextField(label="API Base URL (OpenAI 模式必填)", width=400)
        self.model_name = ft.TextField(label="模型名称 (例如 gpt-4o, gemini-1.5-flash)", value="gemini-1.5-flash",
                                       width=400)
        self.temperature = ft.Slider(min=0, max=1, divisions=10, label="温度: {value}", value=0.1, width=400)

        self.init_ui()
        self.load_data()

    def init_ui(self):
        self.content = ft.Column([
            ft.Text("事务所设置 (Configuration)", size=28, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("核心模型设置", size=20, weight=ft.FontWeight.W_500),
            self.api_provider,
            self.api_key,
            self.base_url,
            self.model_name,
            ft.Text("随机性 (Temperature)"),
            self.temperature,
            ft.Divider(),
            ft.ElevatedButton("保存配置", icon=ft.icons.SAVE, on_click=self.save_data, height=50, width=150),
        ], scroll=ft.ScrollMode.AUTO)

    def load_data(self):
        settings = config_manager.load_settings()
        self.api_provider.value = settings.get("api_provider", "openai")
        self.api_key.value = settings.get("api_key", "")
        self.base_url.value = settings.get("api_base_url", "")
        self.model_name.value = settings.get("model_name", "gemini-1.5-flash")
        self.temperature.value = settings.get("temperature", 0.1)

    def save_data(self, e):
        config_manager.save_settings({
            "api_provider": self.api_provider.value,
            "api_key": self.api_key.value,
            "api_base_url": self.base_url.value,
            "model_name": self.model_name.value,
            "temperature": self.temperature.value
        })
        e.page.snack_bar = ft.SnackBar(ft.Text("配置已保存！"))
        e.page.snack_bar.open = True
        e.page.update()