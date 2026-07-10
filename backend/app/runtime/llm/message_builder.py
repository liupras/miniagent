#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-10
# @description: Message Builder

import base64
import mimetypes

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