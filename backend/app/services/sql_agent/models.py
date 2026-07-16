#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-16
# @description: models

from typing import Optional
from pydantic import BaseModel

class SQLAgentConfig(BaseModel):

    schema_name: str = "main"
    system_prompt_template: Optional[str] = None
    schema_context_prompt_template_1: Optional[str] = None
    schema_context_prompt_2: Optional[str] = None
    schema_context_prompt_3: Optional[str] = None
    get_schema_desc: Optional[str] = None
    sample_data_desc: Optional[str] = None
    execute_sql_desc: Optional[str] = None
    run_python_desc: Optional[str] = None
    para_table_name_desc: Optional[str] = None
    para_limit_desc: Optional[str] = None
    para_sql_desc: Optional[str] = None
    para_code_desc: Optional[str] = None