"""Judge-only tool execution. Evidence and context are local to each invocation."""
import asyncio
from copy import copy
import json
from .exceptions import JudgeConfigurationError, JudgeInvalidResponseError

LAW_TOOL = 'intellectual_property_law_search'
REVISION = '[JudgeAPI V2:2026-09-12-legal-extension]'

def handoff(reason):
    return json.dumps({'decision':'HANDOFF', 'target':None,
        'speech':'当前无法提供有充分检索依据的法律解释，请人工处理。',
        'pending_points':[reason]}, ensure_ascii=False)

def has_material(raw):
    # The bound smart-router tool returns structured chunks, not a free-text answer.
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return (isinstance(data, dict) and not data.get('error')
            and data.get('confidence') != 'empty' and isinstance(data.get('chunks'), list)
            and any(isinstance(c, dict) and isinstance(c.get('text'), str)
                    and c['text'].strip() for c in data['chunks']))
    except (ValueError, TypeError):
        return False

async def invoke_judge(runner, query):
    if REVISION not in runner._system_prompt:
        raise JudgeConfigurationError(params={'reason':'judge_revision_mismatch'})
    agent = runner._agent
    llm = copy(agent.agent_llm)
    llm.preserve_context = True
    messages = [{'role':'system', 'content':runner._system_prompt},
                {'role':'user', 'content':query}]
    # Missing binding does not force ordinary speech checks to fail. The model
    # can identify no pending question; requests for explanation must HANDOFF.
    if LAW_TOOL not in agent.tools_map:
        messages.append({'role':'system', 'content':'法律检索工具不可用。若有待回答法律问题必须 HANDOFF；没有待回答问题才可按 allowed_decisions 决策。'})
    searched = False
    for _ in range(10):
        response = await llm.achat(messages, tool_schema=agent.tool_schemas)
        messages.append(response)
        calls = response.get('tool_calls')
        if not calls:
            raw = response.get('content', '')
            try:
                decision = json.loads(raw).get('decision')
            except (ValueError, AttributeError, TypeError):
                return raw  # Service owns the single format repair.
            if decision == 'EXPLAIN_LAW' and not searched:
                return handoff('法律解释缺少本次有效检索依据。')
            return raw
        for call in calls:
            function = call.get('function', {})
            name = function.get('name')
            # Judges are authorized to retrieve legal sources only.
            if name != LAW_TOOL or name not in agent.tools_map:
                return handoff('所需法律检索工具不可用。')
            try:
                args = function.get('arguments', {})
                if isinstance(args, str):
                    args = json.loads(args)
                if not isinstance(args, dict):
                    return handoff('法律检索参数无效。')
                observation = await agent.tools_map[name].ainvoke(args)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never expose tool exception details or turn failure into NO_ACTION.
                return handoff('法律检索失败，请人工核对法律依据。')
            if not has_material(observation):
                return handoff('法律检索未返回可用依据，请人工核对。')
            searched = True
            content = observation if isinstance(observation, str) else json.dumps(observation, ensure_ascii=False)
            messages.append({'role':'tool', 'tool_call_id':call.get('id', 'law_search'),
                             'name':name, 'content':content})
    raise JudgeInvalidResponseError(params={'reason':'tool_step_limit', 'field':'response'})
