#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-09-17
# @description: Strict JSON decoding shared by integration request and response contracts.

import json


def strict_json(raw, *, max_bytes=None):
    """Decode UTF-8 JSON while rejecting duplicates and non-standard constants."""

    if isinstance(raw, bytes):
        encoded = raw
        raw = raw.decode("utf-8")
    elif isinstance(raw, str):
        encoded = raw.encode("utf-8")
    else:
        raise ValueError("JSON body must be str or bytes")
    if max_bytes is not None and len(encoded) > max_bytes:
        raise ValueError("body_size")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError("invalid JSON constant")

    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=invalid_constant,
    )
