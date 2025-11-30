"""
模块: LLM Factory
基于原 llm.py 改造，移除环境变量依赖，改为参数注入。
"""
import sys
from langchain_core.language_models import BaseLanguageModel


def create_llm(
        provider: str,
        api_key: str,
        model_name: str,
        temperature: float = 0.1,
        base_url: str = None
) -> BaseLanguageModel:
    """
    根据配置创建 LLM 实例
    """
    if not api_key:
        raise ValueError("API Key is missing")

    provider = provider.lower()

    if provider == "google":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            # Google 官方 API 通常不需要 base_url，除非是特殊代理
            return ChatGoogleGenerativeAI(
                model=model_name,
                temperature=temperature,
                google_api_key=api_key,
                transport="rest"
            )
        except ImportError:
            raise ImportError("Please install langchain-google-genai")

    elif provider == "openai":
        try:
            from langchain_openai import ChatOpenAI

            kwargs = {
                "model": model_name,
                "temperature": temperature,
                "api_key": api_key,
            }
            if base_url:
                kwargs["base_url"] = base_url

            return ChatOpenAI(**kwargs)
        except ImportError:
            raise ImportError("Please install langchain-openai")

    else:
        raise ValueError(f"Unsupported provider: {provider}")


def test_connection(llm: BaseLanguageModel) -> str:
    try:
        resp = llm.invoke("Hello, simple test.")
        return str(resp.content)
    except Exception as e:
        raise e