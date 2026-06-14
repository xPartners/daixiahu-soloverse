"""医保垂直大模型基座：统一封装 OpenAI / Qwen / GLM / Ollama 调用。

所有 provider 均走 OpenAI 兼容 API，通过 base_url 切换后端。
"""
from __future__ import annotations

import json
from typing import Optional

from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.core.exceptions import ModelInferenceError


# 不同 provider 的默认模型映射
_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "qwen": "qwen-plus",
    "glm": "glm-4",
    "ollama": "qwen2.5:7b",
}


class LLMClient:
    """统一大模型客户端，兼容 OpenAI / Qwen / GLM / Ollama（均走 OpenAI 兼容 API）。"""

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.provider: str = provider or settings.LLM_PROVIDER
        self.api_key: str = api_key if api_key is not None else settings.LLM_API_KEY
        self.base_url: str = base_url or settings.LLM_BASE_URL
        # 模型优先级：显式传入 > 配置 LLM_MODEL > provider 默认值
        self.model: str = (
            model
            or settings.LLM_MODEL
            or _DEFAULT_MODELS.get(self.provider, "gpt-4o-mini")
        )
        self.temperature: float = settings.LLM_TEMPERATURE
        self.max_tokens: int = settings.LLM_MAX_TOKENS
        # ollama 本地部署通常无需 api_key，给一个占位值避免 SDK 校验报错
        if not self.api_key and self.provider == "ollama":
            self.api_key = "ollama"
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _chat_with_retry(self, **kwargs) -> str:
        """带 tenacity 重试（3 次、指数退避）的底层调用。"""
        resp = self._client.chat.completions.create(model=self.model, **kwargs)
        return resp.choices[0].message.content or ""

    def chat(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
    ) -> str:
        """同步对话调用，带 3 次指数退避重试，失败抛 ModelInferenceError。"""
        kwargs: dict = {
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            return self._chat_with_retry(**kwargs)
        except Exception as exc:
            raise ModelInferenceError(f"大模型调用失败: {exc}") from exc

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """去除 markdown 代码块包裹（```json ... ```）。"""
        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        # 去掉首行 ``` 标记
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # 去掉末尾 ``` 标记
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @staticmethod
    def _parse_json(content: str):
        """解析 JSON 文本，自动去除代码块包裹。"""
        cleaned = LLMClient._strip_code_fences(content)
        return json.loads(cleaned)

    def _inject_json_instruction(self, messages: list[dict]) -> list[dict]:
        """在 system prompt 中追加严格的 JSON 输出要求。"""
        adjusted = [dict(m) for m in messages]
        if adjusted and adjusted[0].get("role") == "system":
            adjusted[0]["content"] = (
                str(adjusted[0].get("content", "")) + "\n请严格以 JSON 格式回复。"
            )
        else:
            adjusted.insert(
                0, {"role": "system", "content": "请严格以 JSON 格式回复。"}
            )
        return adjusted

    def chat_json(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
    ) -> dict:
        """请求 JSON 格式输出并解析为 dict，解析失败时重试一次。

        重试策略：首次调用解析失败后，再调用一次 chat；
        若 chat 调用本身失败（已由 chat 内部重试 3 次）则直接抛出。
        两次解析均失败则抛 ModelInferenceError。
        """
        adjusted = self._inject_json_instruction(messages)
        last_error: Optional[Exception] = None
        for _attempt in range(2):  # 初次 + 重试一次
            try:
                content = self.chat(adjusted, temperature=temperature)
            except ModelInferenceError:
                # chat 调用失败直接上抛
                raise
            try:
                return self._parse_json(content)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                continue
        raise ModelInferenceError(f"JSON 解析失败: {last_error}")


# ---------- 模块级单例 ----------
_llm_instance: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    """获取模块级 LLMClient 单例。"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMClient()
    return _llm_instance
