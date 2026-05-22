#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-19
# @description: Utility functions

from typing import List,Dict

from app.utils.tokens import estimate_tokens

def estimate_messages_tokens(messages: List[Dict]) -> int:
    """
    Calculate the total number of tokens in the message list.
    Here we use a simple approximation by counting the total string length.
    In a production environment, consider using a tokenizer for accurate token counting.
    """
    total_length = 0
    for msg in messages:
        str_all = msg.get("role", "") + msg.get("content", "")
        total_length += estimate_tokens(str_all)
    return total_length

def truncate_messages(messages: List[Dict], max_token: int) -> List[Dict]:
    """
    Prune the message list to ensure the total string length does not exceed `max_token`

    Rules: Preserve system prompts → Preserve from the latest history backwards → Ensure the user's current input is not truncated
    """
    # Detach the system prompt (must be retained).
    system_msg = [msg for msg in messages if msg["role"] == "system"]
    non_system_msgs = [msg for msg in messages if msg["role"] != "system"]

    # Calculate the length of the system prompt
    system_length = estimate_messages_tokens(system_msg)
    remaining_length = max_token - system_length

    if remaining_length <= 0 or not non_system_msgs:
        # Extreme case: System prompts have exceeded the limit, only a portion of system prompts are retained.
        system_msg[0]["content"] = system_msg[0]["content"][:max_token]
        return [system_msg[0]]
    
    # Iterate through non-system messages from back to front (latest messages first), accumulating the length until the upper limit is reached.
    truncated_non_system = []
    current_length = 0
    # First, extract the current user input (the last non-system message) to ensure it is not truncated.
    user_input_msg = non_system_msgs[0] if non_system_msgs else None   
    if user_input_msg:
        user_input_length = estimate_tokens(user_input_msg["content"])
        if user_input_length > remaining_length:
            # Extreme case: If user input exceeds the limit, only a portion of the user input will be retained.
            user_input_msg["content"] = user_input_msg["content"][:remaining_length]
            truncated_non_system.append(user_input_msg)
        else:
            current_length += user_input_length
            truncated_non_system.append(user_input_msg)
            # Then process the historical records (from back to front, i.e., the most recent history is retained first).
            for msg in non_system_msgs[1:]:
                msg_length = estimate_tokens(msg["content"])
                if current_length + msg_length <= remaining_length:
                    truncated_non_system.append(msg)
                    current_length += msg_length
                else:
                    break
        # Reverse the history and restore the original order.
        truncated_non_system = list(reversed(truncated_non_system))
    
    # Merge the final message list
    final_messages = system_msg + truncated_non_system
    return final_messages

if __name__ == "__main__":
    """
    测试用例覆盖场景：
    1. 常规场景：消息总长度未超限制，完整保留
    2. 常规场景：消息总长度超限，保留最新历史+用户输入+系统提示
    3. 边界场景：系统提示长度超限，仅截断系统提示
    """
    
    def test_case(case_name, messages, max_token, expected_length):
        """执行单个测试用例并输出结果"""
        # 深拷贝消息，避免测试用例之间互相影响
        import copy
        test_msgs = copy.deepcopy(messages)
        result = truncate_messages(test_msgs, max_token)
        result_total_tokens = estimate_messages_tokens(result)
        success = result_total_tokens <= max_token and (expected_length is None or result_total_tokens == expected_length)
        status = "PASS" if success else "FAIL"
        print(f"[{status}] {case_name}")
        print(f"  输入消息数: {len(messages)}, 输出消息数: {len(result)}")
        print(f"  输出总Token数: {result_total_tokens}, 最大限制: {max_token}")
        print(f"  输出消息内容: {[{'role': m['role'], 'content': m['content'][:20]+'...' if len(m['content'])>20 else m['content']} for m in result]}")
        print("-" * 80)
        return success

    # 测试用例1：常规场景 - 总长度未超限制
    # 非系统消息第一个是最新用户输入："谢谢"
    test_messages_1 = [
        {"role": "system", "content": "你是一个助手"},  # system: 6 token
        {"role": "user", "content": "谢谢"},            # user: 2 token (最新输入，第一个非系统消息)
        {"role": "assistant", "content": "您好！"},      # assistant: 3 token
        {"role": "user", "content": "你好"}             # user: 2 token
    ]
    test_case("常规场景-总长度未超限制", test_messages_1, 50, 14)

    # 测试用例2：常规场景 - 总长度超限
    # 非系统消息第一个是最新用户输入："问题3"
    test_messages_2 = [
        {"role": "system", "content": "你是一个助手"},  # 6 token
        {"role": "user", "content": "问题3"},          # 3 token (最新输入，第一个非系统消息)
        {"role": "assistant", "content": "回答2"},      # 3 token
        {"role": "user", "content": "问题2"},          # 3 token
        {"role": "assistant", "content": "回答1"},      # 3 token
        {"role": "user", "content": "问题1"}           # 3 token
    ]
    # 预期：system(6) + 问题3(3) + 回答2(3) + 问题2(3) = 15
    test_case("常规场景-总长度超限", test_messages_2, 10, 15)

    # 测试用例3：边界场景 - 系统提示长度超限
    test_messages_3 = [
        {"role": "system", "content": "你是一个非常非常非常长的系统提示，长度超过最大限制"}  # 25 token
    ]
    test_case("边界场景-系统提示长度超限", test_messages_3, 10, 10)

    print("所有测试用例执行完成！")