#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-27
# @description: Prompt

from typing import Dict

from app.repositories.async_prompt import AsyncPromptDatabase

class PromptService:

    def __init__(self, db: AsyncPromptDatabase) -> None:
        self._db = db

    async def get_all_as_dict(self)->Dict[str, Dict[str, str]]:

        prompts = await self._db.get_all()
        prompt_dict = {}
        for p in prompts:
            if p.key not in prompt_dict:
                prompt_dict[p.key] = {}
            prompt_dict[p.key][p.lang] = p.value
            
        return prompt_dict