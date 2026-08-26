#!/usr/bin/python
# -*- coding:utf-8 -*-

import unittest

from app.runtime.conversation.service_conversation import calculate_input_budget
from app.runtime.llm.agent_client import AgentLLM
from app.utils.tokens import TokenCounter


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
        self.token_counter = TokenCounter(
            model="test-model",
            enable_exact_near_limit=False,
        )
        self.llm = AgentLLM(
            client=_FakeLLMClient(),
            model="test-model",
            context_window_tokens=self.context_window_tokens,
            max_output_tokens=self.max_output_tokens,
            token_counter=self.token_counter,
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

        self.assertLessEqual(self.token_counter.count_messages(trimmed), self.input_budget)
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

        self.assertLessEqual(self.token_counter.count_messages(trimmed), self.input_budget)
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

        self.assertLessEqual(self.token_counter.count_messages(trimmed), self.input_budget)
        self.assertEqual([message["role"] for message in trimmed[-2:]], ["assistant", "tool"])
        self.assertEqual(trimmed[-1]["tool_call_id"], "call_1")

    def test_rejects_fixed_prompts_that_leave_no_room_for_a_turn(self):
        messages = [
            {"role": "system", "content": "system-" * 1000},
            {"role": "user", "content": "Hello"},
        ]

        with self.assertRaisesRegex(ValueError, "System prompts"):
            self.llm._fit_messages_to_context(messages)

    def test_exact_counter_receives_the_sanitized_provider_payload(self):
        calls = []

        def exact_counter(**kwargs):
            calls.append(kwargs)
            return 10

        llm = AgentLLM(
            client=_FakeLLMClient(),
            model="test-model",
            context_window_tokens=self.context_window_tokens,
            max_output_tokens=self.max_output_tokens,
            token_counter=TokenCounter(
                model="test-model",
                exact_threshold_ratio=0.01,
                exact_counter=exact_counter,
            ),
        )
        messages = [
            {
                "role": "user",
                "content": "Use the tool",
                "_internal_trace": "must not be sent",
            }
        ]

        provider_messages = llm._build_messages(
            messages,
            tool_schema=[{"type": "function", "function": {"name": "search"}}],
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["messages"], provider_messages)
        self.assertTrue(all(
            not any(str(key).startswith("_") for key in message)
            for message in provider_messages
        ))
        self.assertIn("search", provider_messages[0]["content"])

    def test_tokenizer_runs_only_for_original_and_final_payload_boundaries(self):
        exact_calls = []
        lightweight = TokenCounter(enable_exact_near_limit=False)

        def exact_counter(**kwargs):
            exact_calls.append(kwargs["messages"])
            return lightweight.count_messages(kwargs["messages"])

        llm = AgentLLM(
            client=_FakeLLMClient(),
            model="test-model",
            context_window_tokens=self.context_window_tokens,
            max_output_tokens=self.max_output_tokens,
            token_counter=TokenCounter(
                model="test-model",
                exact_threshold_ratio=0.01,
                exact_counter=exact_counter,
            ),
        )
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "old-" + "x" * 5000},
            {"role": "assistant", "content": "answer-" + "y" * 5000},
            {"role": "user", "content": "latest question"},
        ]

        trimmed = llm._fit_messages_to_context(messages)

        assert len(exact_calls) == 2
        assert exact_calls[0] == messages
        assert exact_calls[1] == trimmed
        assert len(trimmed) < len(messages)


if __name__ == "__main__":
    unittest.main()
