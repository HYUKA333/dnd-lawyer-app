import os
import json
import shutil
import subprocess
import logging
import re
from bs4 import BeautifulSoup
import html2text

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CHMProcessor:
    def __init__(self):
        self.base_dir = os.getcwd()
        self.temp_dir = os.path.join(self.base_dir, "temp_chm")
        self.output_dir = os.path.join(self.base_dir, "data")
        self.seven_zip_path = self._get_7zip_path()
        self.config = None
        self.chm_source_dir = None
        # 严格对应 analyze_chm.py 的阈值
        self.SPLIT_HEURISTIC_THRESHOLD = 9

    def _get_7zip_path(self):
        """获取 7zip 路径，优先使用 bin 目录"""
        bin_path = os.path.join(self.base_dir, "bin", "7za.exe")
        if os.path.exists(bin_path):
            return bin_path
        # Fallback 到系统命令
        return "7za"

    def process_chm(self, file_path):
        """
        阶段 1: 解包与分析 (对应 analyze_chm.py)
        """
        # 1. 清理环境
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir)

        self.chm_source_dir = os.path.join(self.temp_dir, "source")

        # 2. 解包
        logger.info(f"正在解包 {file_path}...")
        try:
            # 使用 list 传参防止路径空格问题
            subprocess.run(
                [self.seven_zip_path, "x", file_path, f"-o{self.chm_source_dir}"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('gbk', errors='ignore') if e.stderr else "Unknown error"
            raise Exception(f"7zip解包失败: {err_msg}")

        # 3. 查找 HHC 索引文件
        hhc_file = None
        for root, _, files in os.walk(self.chm_source_dir):
            for f in files:
                if f.lower().endswith('.hhc'):
                    hhc_file = os.path.join(root, f)
                    break
            if hhc_file: break

        if not hhc_file:
            raise Exception("未找到 .hhc 索引文件，无法分析结构。")

        # 4. 生成配置树
        self.config = self._generate_config_logic(hhc_file)
        return self.config

    def _generate_config_logic(self, hhc_path):
        """
        核心分析逻辑：解析 HHC -> 应用启发式算法 -> 生成 Config
        """
        content = self._read_file_safe(hhc_path)
        if not content:
            raise Exception("无法读取 HHC 文件内容")

        soup = BeautifulSoup(content, 'html.parser')

        # 解析 HHC 获取待处理的文件列表
        items = self._parse_hhc_items(soup)

        tree_rules = {}
        for item in items:
            name = item['name']
            rel_path = item['path']

            # === 核心算法：启发式判断 Split 策略 (analyze_chm.py) ===
            split_by = self._analyze_split_strategy_strict(rel_path)

            tree_rules[name] = {
                "path": rel_path,
                "action": "process",  # 默认选中
                "split_by": split_by
            }

        return {
            "common_config": {
                "base_url": "chm://",
                "selector": "body"
            },
            "tree_processing_rules": tree_rules
        }

    def _parse_hhc_items(self, soup):
        """
        解析 HHC 结构。
        为了 UI 展示简洁，目前只提取第一层级的有效 HTML 节点。
        """
        items = []

        # 尝试找到根 UL
        root_ul = soup.find('ul')
        target_container = root_ul if root_ul else soup

        # 仅遍历直接子节点以获取“根目录”概念
        for li in target_container.find_all('li', recursive=False):
            obj = li.find('object', type="text/sitemap")
            if not obj: continue

            name_param = obj.find('param', {'name': 'Name'})
            local_param = obj.find('param', {'name': 'Local'})

            if name_param and local_param:
                path = local_param['value'].replace('\\', '/').lstrip('/')
                # 忽略非 HTML 资源
                if not path.lower().endswith(('.htm', '.html')):
                    continue

                items.append({
                    'name': name_param['value'],
                    'path': path
                })

        # 如果 HHC 结构太乱找不到 recursive=False 的，回退到搜索所有 (Fallback)
        if not items:
            seen_paths = set()
            for obj in soup.find_all('object', type="text/sitemap"):
                name_param = obj.find('param', {'name': 'Name'})
                local_param = obj.find('param', {'name': 'Local'})
                if name_param and local_param:
                    path = local_param['value'].replace('\\', '/').lstrip('/')
                    if path in seen_paths or not path.lower().endswith(('.htm', '.html')):
                        continue
                    seen_paths.add(path)
                    items.append({'name': name_param['value'], 'path': path})
            # 限制数量防止 UI 卡死
            items = items[:100]

        return items

    def _analyze_split_strategy_strict(self, relative_path):
        """
        [严格复刻] analyze_chm.py 的启发式算法
        优先级: H1 -> H2 -> H3 -> H4
        """
        full_path = os.path.join(self.chm_source_dir, relative_path)
        if not os.path.exists(full_path):
            return None

        content = self._read_file_safe(full_path)
        if not content: return None

        soup = BeautifulSoup(content, 'html.parser')

        # 统计标签数量
        h_counts = [len(soup.find_all(f'h{i}')) for i in range(1, 7)]

        # 严格的优先级判断 (analyze_chm.py 逻辑)
        if h_counts[0] > self.SPLIT_HEURISTIC_THRESHOLD:  # H1
            return "h1"
        elif h_counts[1] > self.SPLIT_HEURISTIC_THRESHOLD:  # H2
            return "h2"
        elif h_counts[2] > self.SPLIT_HEURISTIC_THRESHOLD:  # H3
            return "h3"
        elif h_counts[3] > self.SPLIT_HEURISTIC_THRESHOLD:  # H4
            return "h4"
        else:
            return None

    def generate_library(self):
        """
        阶段 2: 打包 (对应 package_json.py)
        """
        if not self.config:
            raise Exception("配置未就绪，请先运行分析")

        output_json_path = os.path.join(self.output_dir, "rules_data.json")
        os.makedirs(self.output_dir, exist_ok=True)

        rules = self.config.get("tree_processing_rules", {})
        all_data = []

        for name, rule in rules.items():
            if rule.get("action") != "process":
                continue

            entries = self._process_node_package(
                title=name,
                relative_path=rule['path'],
                split_by=rule.get('split_by')
            )
            all_data.extend(entries)

        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)

        return output_json_path

    def _process_node_package(self, title, relative_path, split_by):
        """处理单个文件节点：读取 -> 正则分割 -> Md转换"""
        full_path = os.path.join(self.chm_source_dir, relative_path)
        if not os.path.exists(full_path):
            return []

        html_content = self._read_file_safe(full_path)
        if not html_content: return []

        # 1. Regex 分割 (复刻 V3/V5)
        if split_by:
            chunks = self._split_content_regex(html_content, split_by)
        else:
            chunks = [{"sub_title": "", "content": html_content}]

        entries = []
        for chunk in chunks:
            # 2. Html2Text 转换
            md_text = self._convert_html_to_md(chunk["content"])

            if not md_text.strip(): continue

            # 构建完整标题
            final_title = title
            if chunk["sub_title"] and chunk["sub_title"] != "Intro":
                final_title = f"{title} - {chunk['sub_title']}"

            entries.append({
                "title": final_title,
                "content": md_text,
                "source": relative_path
            })

        return entries

    def _split_content_regex(self, html_content, tag_name):
        """
        [关键逻辑] 基于正则的字符串分割 (复刻 package_json.py)
        保留 <tag>...</tag> 及其内容。
        """
        # Pattern: (<tag\b[^>]*>.*?</tag>)
        # re.DOTALL 确保 . 匹配换行符
        # re.IGNORECASE 忽略大小写
        pattern = f"(<{tag_name}\\b[^>]*>.*?</{tag_name}>)"

        parts = re.split(pattern, html_content, flags=re.DOTALL | re.IGNORECASE)

        results = []

        # Part 0 是第一个 header 之前的内容 (Intro)
        if parts[0].strip():
            results.append({"sub_title": "Intro", "content": parts[0]})

        # 后续是 delimiter (标题HTML) 和 content (正文) 交替
        # parts[1] = header, parts[2] = body, parts[3] = header, ...
        for i in range(1, len(parts), 2):
            if i + 1 >= len(parts): break  # 防止越界

            header_html = parts[i]
            body_html = parts[i + 1]

            # 提取纯文本标题
            soup_header = BeautifulSoup(header_html, 'html.parser')
            clean_title = soup_header.get_text(" ", strip=True)

            # 组合内容：将 header 放回 body 开头，以便 Markdown 保留层级
            combined = header_html + "\n" + body_html

            results.append({
                "sub_title": clean_title,
                "content": combined
            })

        return results

    def _convert_html_to_md(self, html_content):
        """配置 html2text (复刻 package_json.py)"""
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.ignore_tables = False  # 必须保留表格
        h.body_width = 0  # 不强制折行
        h.protect_links = True
        h.unicode_snob = True

        try:
            return h.handle(html_content)
        except Exception as e:
            logger.error(f"Markdown conversion error: {e}")
            return BeautifulSoup(html_content, 'html.parser').get_text()

    def _read_file_safe(self, path):
        """多编码读取尝试 (复刻 analyze_chm.py 的健壮性)"""
        try:
            with open(path, 'rb') as f:
                raw = f.read()
            # 常见中文编码尝试顺序
            encodings = ['utf-8-sig', 'utf-8', 'gb18030', 'gbk', 'big5', 'utf-16']
            for enc in encodings:
                try:
                    return raw.decode(enc)
                except:
                    continue
            return raw.decode('utf-8', errors='ignore')
        except Exception:
            return None