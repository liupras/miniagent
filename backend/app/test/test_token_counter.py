#!/usr/bin/python
# -*- coding:utf-8 -*-

import unittest

from app.utils.tokens import TokenCounter, estimate_tokens


class TokenCounterTests(unittest.TestCase):
    def test_lightweight_counter_handles_short_and_mixed_text(self):
        counter = TokenCounter(enable_exact_near_limit=False)

        self.assertEqual(counter.count_text(""), 0)
        self.assertGreaterEqual(counter.count_text("a"), 1)
        self.assertGreaterEqual(counter.count_text("中"), 1)
        self.assertGreater(counter.count_text("hello 世界 😀 {}"), 0)
        self.assertGreaterEqual(estimate_tokens("a"), 1)

    def test_message_counter_includes_tool_protocol_metadata(self):
        counter = TokenCounter(enable_exact_near_limit=False)
        plain = [{"role": "assistant", "content": "working"}]
        with_tool_call = [
            {
                "role": "assistant",
                "content": "working",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": '{"query":"miniagent"}',
                        },
                    }
                ],
            }
        ]

        self.assertGreater(
            counter.count_messages(with_tool_call),
            counter.count_messages(plain),
        )

    def test_exact_counter_is_not_called_below_threshold(self):
        calls = []

        def exact_counter(**kwargs):
            calls.append(kwargs)
            return 7

        counter = TokenCounter(
            model="test-model",
            exact_threshold_ratio=0.85,
            exact_counter=exact_counter,
        )
        result = counter.count_text("short", budget=1000)

        self.assertGreater(result, 0)
        self.assertEqual(calls, [])

    def test_exact_counter_is_called_near_limit(self):
        calls = []

        def exact_counter(**kwargs):
            calls.append(kwargs)
            return 23

        counter = TokenCounter(
            model="test-model",
            exact_threshold_ratio=0.5,
            exact_counter=exact_counter,
        )
        result = counter.count_messages(
            [{"role": "user", "content": "x" * 1000}],
            budget=100,
        )

        self.assertEqual(result, 23)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "test-model")
        self.assertIn("messages", calls[0])

    def test_exact_counter_failure_falls_back_to_lightweight(self):
        def failing_counter(**kwargs):
            raise RuntimeError("tokenizer unavailable")

        counter = TokenCounter(
            model="test-model",
            exact_threshold_ratio=0.1,
            exact_counter=failing_counter,
        )
        without_budget = counter.count_text("fallback text")
        near_limit = counter.count_text("fallback text", budget=1)

        self.assertEqual(near_limit, without_budget)

    def test_invalid_threshold_and_budget_are_rejected(self):
        with self.assertRaises(ValueError):
            TokenCounter(exact_threshold_ratio=0)

        counter = TokenCounter(model="test-model")
        with self.assertRaises(ValueError):
            counter.count_text("text", budget=0)
        with self.assertRaises(ValueError):
            counter.count_messages([], budget=0)


if __name__ == "__main__":
    unittest.main()
