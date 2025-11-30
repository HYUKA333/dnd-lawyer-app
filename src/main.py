import flet as ft
import sys
import os

# 确保能找到 src 模块
sys.path.append(os.getcwd())

from src.ui.app_layout import AppLayout


def main(page: ft.Page):
    page.title = "DND Lawyer Desktop"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 1200
    page.window_height = 800
    page.padding = 0  # 让布局填满

    # 加载主布局
    layout = AppLayout(page)
    page.add(layout)


if __name__ == "__main__":
    ft.app(target=main)