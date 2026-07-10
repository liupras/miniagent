#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-19
# @description: General LLM client

from litellm import completion, acompletion, embedding,aembedding
from typing import Any, AsyncGenerator, Optional,Dict,List,Generator,Union

from loguru import logger

from .stream_parser import StreamParser
from .models import LLMClientError,LLMResponse

Message = Dict[str, Any]

import litellm
litellm._turn_on_debug()
   
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

        if "temperature" not in kwargs:
            params["temperature"] = self.temperature        

        return params    
       
    def chat(
        self,
        model: str,
        messages: List[Message],
        **kwargs
    ) -> LLMResponse:
        """Normal mode call"""
        logger.debug(f"Calling Model: {model},Message count: {len(messages)}.")
        
        try:
            response = completion(
                **self._completion_kwargs(
                    model=model,
                    messages=messages,
                    **kwargs,
                )
            )

            return self._build_response(
                response,
                model,                
            )
        except Exception as e:
            logger.error(f"[LLMClient] API Call failed: {str(e)}")
            raise LLMClientError(f"API Call failed: {str(e)}")
    
    async def achat(
        self,
        model: str,
        messages: List[Message],
        **kwargs
    ) -> LLMResponse:
        """Normal mode call"""
        logger.debug(f"Calling Model: {model},Message count: {len(messages)}.")
        
        response = await acompletion(
            **self._completion_kwargs(
                model=model,
                messages=messages,
                **kwargs,
            )
        )

        return self._build_response(
            response,
            model,            
        )    

    def _build_response(
        self,
        response,
        model: str,        
    ) -> LLMResponse:
        
        msg = response.choices[0].message
        content = getattr(
            msg,
            "content",
            ""
        ) or ""

        thinking_content=None
        if self.hide_thinking:
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
    
    def stream(
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

        parser = StreamParser(hide_thinking)
        for chunk in response:
            token = parser.parse(chunk)

            if token:
                yield token        
    
    async def astream(
        self,
        model: str,
        messages: List[Message],
        hide_thinking: bool = True,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Streaming mode call"""
        logger.debug(f"Streaming call model: {model}, Message count: {len(messages)}.")
        
        response = await acompletion(
            stream=True,
            **self._completion_kwargs(
                model=model,
                messages=messages,
                **kwargs,
            )
        )

        parser = StreamParser(hide_thinking)
        async for chunk in response:
            token = parser.parse(chunk)

            if token:
                yield token

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
        
    async def aembed(
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
            response = await aembedding(
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