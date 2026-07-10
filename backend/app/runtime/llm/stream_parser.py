#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-10
# @description: Stream Parser

class StreamParser:

    def __init__(self, hide_thinking):
        self.hide_thinking = hide_thinking
        self.in_think = False

    def parse(self, chunk):

        if not chunk.choices:
            return None

        delta = chunk.choices[0].delta

        reasoning = getattr(
            delta,
            "reasoning_content",
            None
        )

        if reasoning:
            if self.hide_thinking:
                return None
            return reasoning

        content = getattr(
            delta,
            "content",
            None
        )

        if not content:
            return None

        if self.hide_thinking:

            if content == "<think>":
                self.in_think = True
                return None

            if content == "</think>":
                self.in_think = False
                return None

            if self.in_think:
                return None

        return content