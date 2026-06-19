#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-19
# @description: General LLM client

from litellm import completion, embedding
from openai import OpenAI
from typing import Any, Optional,Dict,List,Generator,Union
import base64
import mimetypes
from loguru import logger

Message = Dict[str, Any]

def generate_stream_response(generator: Generator[str, None, None]):
    """Convert the generator to SSE streaming response format"""
    for chunk in generator:
        if chunk:
            # SSE format: data: content\n\n
            yield f"data: {chunk}\n\n"
    # Streaming end marker
    yield "data: [DONE]\n\n"

class LLMClientError(Exception):
    """LLM client custom exceptions"""
    pass

class LLMResponse:
    """LLM response wrapper class"""
    
    def __init__(
        self,
        content: str,
        thinking: Optional[str] = None,
        model: Optional[str] = None,
        usage: Optional[Dict] = None,

        tool_calls: Optional[List] = None,
        images: Optional[List] = None,
        audio: Optional[List] = None,
        videos: Optional[List] = None,

        raw_response: Any = None,
    ):
        """
        Initialize LLM response
        """
        self.content = content
        self.thinking = thinking
        self.model = model
        self.usage = usage or {}

        # multimodal extensions
        self.tool_calls = tool_calls or []
        self.images = images or []
        self.audio = audio or []
        self.videos = videos or []

        self.raw_response = raw_response
    
    def __str__(self) -> str:
        """String representation (only the main content is returned)"""
        return self.content
    
    def __repr__(self) -> str:
        """Detailed description"""
        return f"LLMResponse(content_len={len(self.content)}, has_thinking={self.thinking is not None})"
    
    def get_full_response(self) -> str:
        """Get the complete response (including thinking)."""
        if self.thinking:
            return f"[Thinking]\n{self.thinking}\n\n[Response]\n{self.content}"
        return self.content
    
class MessageBuilder:
    """
    Optional helper.
    Old messages remain compatible.
    """

    @staticmethod
    def text(text: str):
        return {
            "type": "text",
            "text": text
        }

    @staticmethod
    def image_url(url: str):
        return {
            "type": "image_url",
            "image_url": {
                "url": url
            }
        }

    @staticmethod
    def image_file(path: str):
        mime = mimetypes.guess_type(path)[0]
        mime = mime or "image/png"

        with open(path, "rb") as f:
            b64 = base64.b64encode(
                f.read()
            ).decode()

        return {
            "type": "image_url",
            "image_url": {
                "url":
                    f"data:{mime};base64,{b64}"
            }
        }

    @staticmethod
    def input_audio(
            data_base64: str,
            fmt: str = "wav"
    ):
        return {
            "type": "input_audio",
            "input_audio": {
                "data": data_base64,
                "format": fmt
            }
        }

    @staticmethod
    def video_url(url: str):
        return {
            "type": "video_url",
            "video_url": {
                "url": url
            }
        }
    

class LLMClient:
    """
    General-purpose LLM client, supporting multiple mainstream LLM providers
    """

    def __init__(
            self, 
            base_url:str, 
            api_key:Optional[str] = None, 
            temperature: float = 0.7,
            hide_thinking: bool = True,
        ):
        """
        Initialize LLM client

        :param base_url: API address, e.g., "http://localhost:8000/v1"
        :param api_key: API key (any string can be used for Ollam, for others it depends on the provider)
        :param temperature: Sampling temperature ([0-1], the larger the value, the higher the randomness)
        :param hide_thinking: Should the "thinking" section be hidden in the returned results?
        """

        self.base_url = base_url
        if not base_url:
            raise LLMClientError("Missing base_url, please provide a valid base_url!")
        self.api_key = api_key
        self.temperature = (
            temperature
            if temperature is not None
            else 0.7
        )
        self.hide_thinking = hide_thinking

    def _completion_kwargs(
            self,
            model: str,
            messages: List[Message],
            **kwargs,
    ):
        params = {
            "model": model,
            "messages": messages,
            **kwargs,
        }

        if self.api_key:
            params["api_key"] = self.api_key

        if self.base_url:
            params["api_base"] = self.base_url

        return params
    
    def chat(
            self, 
            model:str, 
            messages:List[Message], 
            stream:bool=False, 
            hide_thinking: Optional[bool] = None,
            **kwargs
        )-> Union[LLMResponse,str, Generator[str, None, None]]:
        """
        chat with model

        :param model: Model name, e.g., "qwen3" or "gpt-4o-mini"
        :param messages: Message list in the format [{"role": "user", "content": "Hello"}]
        :param stream: Whether to use streaming mode
        :param hide_thinking: Should the "thinking" section be hidden in the returned results?
        :param kargs: Other parameters supported by the model,eg. max_tokens, top_p, etc.

        :return: Response string or generator(if streaming mode)

        """

        if "temperature" not in kwargs:
            kwargs["temperature"] = self.temperature
        if hide_thinking is None:
            hide_thinking = self.hide_thinking
        
        try:
            if stream:
                return self._chat_stream(model, messages,hide_thinking, **kwargs)
            else:
                return self._chat_normal(model, messages,hide_thinking, **kwargs)
        except Exception as e:
            logger.error(f"[LLMClient] API Call failed: {str(e)}")
            raise LLMClientError(f"API Call failed: {str(e)}")
        
    def _chat_normal(
        self,
        model: str,
        messages: List[Message],
        hide_thinking: bool = True,
        **kwargs
    ) -> str:
        """Normal mode call"""
        logger.debug(f"Calling Model: {model},Message count: {len(messages)}.")
        
        response = completion(
            **self._completion_kwargs(
                model=model,
                messages=messages,
                **kwargs,
            )
        )

        msg = response.choices[0].message
        content = getattr(
            msg,
            "content",
            ""
        ) or ""

        thinking_content=None
        if hide_thinking:
            content,thinking_content = self._strip_thinking(content)

        usage = {}
        if getattr(response, "usage", None):
            usage = {
                "prompt_tokens":
                    response.usage.prompt_tokens,
                "completion_tokens":
                    response.usage.completion_tokens,
                "total_tokens":
                    response.usage.total_tokens,
            }

        tool_calls = getattr(
            msg,
            "tool_calls",
            None
        )         

        return LLMResponse(
                content=content,
                thinking=thinking_content,
                model=model,
                usage=usage,
                tool_calls=tool_calls,
                raw_response=response
            )
    
    def _chat_stream(
        self,
        model: str,
        messages: List[Message],
        hide_thinking: bool = True,
        **kwargs
    ) -> Generator[str, None, None]:
        """Streaming mode call"""
        logger.debug(f"Streaming call model: {model}, Message count: {len(messages)}.")
        
        response = completion(
            stream=True,
            **self._completion_kwargs(
                model=model,
                messages=messages,
                **kwargs,
            )
        )
        
        in_think = False

        for chunk in response:

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            reasoning = getattr(
                delta,
                "reasoning_content",
                None
            )

            if reasoning:
                if hide_thinking:
                    continue
                yield reasoning
                continue

            content = getattr(
                delta,
                "content",
                None
            )

            if not content:
                continue

            if hide_thinking:
                if content == "<think>":
                    in_think = True
                    continue
                if content == "</think>":
                    in_think = False
                    continue
                if in_think:
                    continue

            yield content    

    def embed(
        self,
        model: str,
        texts: Union[str, List[str]],
    ) -> List[List[float]]:
        """
        Call the OpenAI-compatible /embeddings endpoint.
        """
        if isinstance(texts, str):
            texts = [texts]
        try:
            response = embedding(
                model=model,
                input=texts,
                api_key=self.api_key,
                api_base=self.base_url,
            )
            return [
                item["embedding"]
                for item in response.data
            ]
        except Exception as e:
            logger.error(f"[LLMClient] Embedding call failed: {str(e)}")
            raise LLMClientError(f"Embedding call failed: {str(e)}")
        
    def _strip_thinking(self, content: str) -> str:
        import re
        main_content = content
        thinking_content = ""
                
         # Try to extract the <thinking>...</thinking> tag.
        if "<thinking>" in content and "</thinking>" in content:
            thinking_match = re.search(
                r'<thinking>(.*?)</thinking>',
                content,
                re.DOTALL
            )
            if thinking_match:
                thinking_content = thinking_match.group(1).strip()
                # Remove the "thinking" section from the main content.
                main_content = re.sub(
                    r'<thinking>.*?</thinking>\s*',
                    '',
                    content,
                    flags=re.DOTALL
                ).strip()

        return main_content,thinking_content

if __name__ == '__main__':
    model_name = "dashscope/qwen-plus"
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key=""
    llm = LLMClient(base_url=base_url, api_key=api_key)

    '''
    print("streaming mode：", end="", flush=True)
    for token in llm.chat(
        model=model_name,
        messages=[{"role": "user", "content": "用少于1000个字总结《西游记》"}],
        stream=True
    ):
        print(token, end="", flush=True)
    '''

    print()  # new line after streaming output

    result = llm.chat(model_name, [{"role": "user", "content": "用李白的风格给我写一首描写饮酒的诗"}])
    print("common mode:\n", result)