#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-19
# @description: General LLM client

from openai import OpenAI,OpenAIError
from typing import Optional,Dict,List,Generator,Union
from loguru import logger

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
        usage: Optional[Dict] = None
    ):
        """
        Initialize LLM response
        
        :param content: Main content
        :param thinking: Reasoning process
        :param model: Model name
        :param usage: Token usage statistics
        """
        self.content = content
        self.thinking = thinking
        self.model = model
        self.usage = usage or {}
    
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

class LLMClient:
    """
    General-purpose LLM client, supporting multiple mainstream LLM providers

    Supported providers:
    - OpenAI, Anthropic, Mistral, Gemini, Cohere
    - xAI, OpenRouter, Ollama, Alibaba Cloud, vLLM
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
        self.temperature = temperature        
        if not temperature:
            self.temperature = 0.7
        self.hide_thinking = hide_thinking

        if not api_key:
            api_key = "none"

        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(
            self, 
            model:str, 
            messages:List[Dict[str, str]], 
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

        # If the user does not provide a temperature value, the default value will be used. 
        if "temperature" not in kwargs:
            kwargs["temperature"] = self.temperature
        
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
        messages: List[Dict[str, str]],
        hide_thinking: bool = True,
        **kwargs
    ) -> str:
        """Normal mode call"""
        logger.debug(f"Calling Model: {model},Message count: {len(messages)}.")
        
        fixed_messages = []
        for msg in messages:
            m = msg.copy()
            # Ollama does not accept content as None; it must be converted to an empty string.
            if m.get("content") is None:
                m["content"] = ""
            fixed_messages.append(m)

        response = self.client.chat.completions.create(
            model=model,
            messages=fixed_messages,
            **kwargs
        )

        # Extract usage information
        usage = None
        if hasattr(response, 'usage') and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }

        content = response.choices[0].message.content
        thinking_content=None
        if hide_thinking:
            content,thinking_content = self._strip_thinking(content)

        return LLMResponse(
                content=content,
                thinking=thinking_content,
                model=model,
                usage=usage
            )
    
    def _chat_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        hide_thinking: bool = True,
        **kwargs
    ) -> Generator[str, None, None]:
        """Streaming mode call"""
        logger.debug(f"Streaming call model: {model}, Message count: {len(messages)}.")
        
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )
        
        if hide_thinking:
            """!!!This is a simplified approach, 
            and it may sometimes fail because the empty string itself is not returned all at once. 
            I'll improve it later when I have time."""
            in_think = False
            is_first_line = False
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content == "<think>":
                    in_think = True
                elif content == "</think>":
                    in_think = False
                    is_first_line = True
                else:
                    if not in_think:
                        if is_first_line and content == '\n\n':
                            is_first_line = False
                        else:
                            yield content
        else:
            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    def _strip_thinking(self, content: str) -> str:
        import re
        main_content = content
                
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

    def embed(
        self,
        model: str,
        texts: Union[str, List[str]],
    ) -> List[List[float]]:
        """
        Call the OpenAI-compatible /embeddings endpoint.

        Works with Ollama, vLLM, and any provider that exposes
        POST /v1/embeddings (OpenAI format).

        :param model:  Embedding model name, e.g. "bge-large-zh" or
                       "nomic-embed-text" (must be pulled in Ollama first).
        :param texts:  A single string or a list of strings to embed.
        :return:       List of float vectors, one per input text.
        """
        if isinstance(texts, str):
            texts = [texts]
        try:
            response = self.client.embeddings.create(model=model, input=texts)
            # OpenAI SDK returns items sorted by index
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"[LLMClient] Embedding call failed: {str(e)}")
            raise LLMClientError(f"Embedding call failed: {str(e)}")

if __name__ == '__main__':
    model_name = "qwen-plus"
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key="sk-4f4a8e428f62464d96a09a59cd436deb"
    llm = LLMClient(base_url=base_url, api_key=api_key)

    print("streaming mode：", end="", flush=True)
    for token in llm.chat(
        model=model_name,
        messages=[{"role": "user", "content": "用少于1000个字总结《西游记》"}],
        stream=True
    ):
        print(token, end="", flush=True)

    print()  # new line after streaming output

    result = llm.chat(model_name, [{"role": "user", "content": "用李白的风格给我写一首描写饮酒的诗"}])
    print("common mode:\n", result)