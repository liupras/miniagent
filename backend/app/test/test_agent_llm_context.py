#!/usr/bin/python
# -*- coding:utf-8 -*-

import unittest

from app.runtime.conversation.service_conversation import calculate_input_budget
from app.runtime.llm.agent_client import AgentLLM
from app.runtime.llm.func import estimate_chat_payload_tokens


class _FakeLLMClient:
    max_output_tokens = 100


class AgentLLMContextTests(unittest.TestCase):
    def setUp(self):
        self.context_window_tokens = 1400
        self.max_output_tokens = 100
        self.input_budget = calculate_input_budget(
            self.context_window_tokens,
            self.max_output_tokens,
        )
        self.llm = AgentLLM(
            client=_FakeLLMClient(),
            model="test-model",
            context_window_tokens=self.context_window_tokens,
            max_output_tokens=self.max_output_tokens,
        )

    def test_keeps_messages_unchanged_when_they_fit(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]

        self.assertEqual(self.llm._fit_messages_to_context(messages), messages)

    def test_discards_old_turns_before_latest_turn(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "old-question-" + "x" * 1800},
            {"role": "assistant", "content": "old-answer-" + "y" * 1800},
            {"role": "user", "content": "latest-question"},
            {"role": "assistant", "content": "latest-answer"},
        ]

        trimmed = self.llm._fit_messages_to_context(messages)

        self.assertLessEqual(estimate_chat_payload_tokens(trimmed), self.input_budget)
        self.assertNotIn(messages[1], trimmed)
        self.assertEqual(trimmed[-2:], messages[-2:])

    def test_truncates_large_tool_result_without_orphaning_it(self):
        assistant = {
            "role": "assistant",
            "content": '{"tool_calls": [{"id": "call_1"}]}',
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search", "arguments": "{}"},
                }
            ],
        }
        tool = {
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "search",
            "content": "result-" * 1000,
        }
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Find this"},
            assistant,
            tool,
        ]

        trimmed = self.llm._fit_messages_to_context(messages)

        self.assertLessEqual(estimate_chat_payload_tokens(trimmed), self.input_budget)
        assistant_index = next(
            index for index, message in enumerate(trimmed)
            if message.get("role") == "assistant"
        )
        self.assertEqual(trimmed[assistant_index + 1]["role"], "tool")
        self.assertEqual(trimmed[assistant_index + 1]["tool_call_id"], "call_1")
        self.assertIn("[Content truncated", trimmed[assistant_index + 1]["content"])

    def test_long_user_message_does_not_discard_latest_tool_exchange(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "question-" * 1000},
            {
                "role": "assistant",
                "content": '{"tool_calls": [{"id": "call_1"}]}',
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "search",
                "content": "latest observation",
            },
        ]

        trimmed = self.llm._fit_messages_to_context(messages)

        self.assertLessEqual(estimate_chat_payload_tokens(trimmed), self.input_budget)
        self.assertEqual([message["role"] for message in trimmed[-2:]], ["assistant", "tool"])
        self.assertEqual(trimmed[-1]["tool_call_id"], "call_1")

    def test_rejects_fixed_prompts_that_leave_no_room_for_a_turn(self):
        messages = [
            {"role": "system", "content": "system-" * 1000},
            {"role": "user", "content": "Hello"},
        ]

        with self.assertRaisesRegex(ValueError, "System prompts"):
            self.llm._fit_messages_to_context(messages)


if __name__ == "__main__":
    unittest.main()
