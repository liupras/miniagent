#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-25
# @description: utility functions for the application

def estimate_tokens(text: str, model_family="qwen") -> int:
    """
    Calculate the number of tokens in a string.
    Here we use a simple approximation by counting the string length.
    """
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    
    # Empirical coefficients of different models
    coefficients = {
        "gpt": (1.5, 4),      # OpenAI
        "claude": (1.3, 3.8), # Anthropic
        "qwen": (1.2, 4),     # 通义千问
        "glm": (1.4, 4),      # 智谱
    }
    
    cn_coef, en_coef = coefficients.get(model_family, (1.5, 4))
    estimated = int(chinese_chars / cn_coef + other_chars / en_coef)
    
    # Conservative estimate: +10% buffer
    return int(estimated * 1.1)