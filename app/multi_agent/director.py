# -*- coding: utf-8 -*-
# @Time    : 2026/2/17 00:44
# @Author  : yangyuexiong
# @Email   : yang6333yyx@126.com
# @File    : director.py
# @Software: PyCharm
from http.client import responses
from operator import add
from typing import TypedDict, Annotated

from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.config import get_stream_writer

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key="sk-10dda2d7b42847a49e6e78d94e3eab33",
    base_url="https://api.deepseek.com"
)


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add]
    type: str


def other_node(state: State):
    print(">>> other_node")
    writer = get_stream_writer()
    writer({"node", ">>> other_node"})
    return {
        "messages": [HumanMessage(content="无法应答...")],
        "type": "other",
    }


def supervisor_node(state: State):
    print(">>> supervisor_node")
    writer = get_stream_writer()
    writer({"node", ">>> supervisor_node"})

    system_prompt = """你是一个客服助手，负责用户问题分类，并将任务分配给其他Agent执行。
    如果用户的问题和旅游路线规划相关，返回 travel
    如果用户的问题是希望讲一个笑话，返回 joke 
    如果用户的问题是希望对一个对联，返回 couplet
    如果是其他问题，返回 other
    除了以上的选项外，不要返回其他内容。
    """

    prompts = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": state["messages"][0]},
    ]

    if "type" in state:
        writer({"supervisor_step": f"已获得 {state["type"]} 智能体处理结果"})
        return {"type": END}
    else:
        response = llm.invoke(prompts)
        res = response.content
        writer({"supervisor_step": f">>> {res}"})
        if res in ["travel", "joke", "couplet", "other"]:
            return {"type": res}
        else:
            raise ValueError("大模型返回 type 异常")


def travel_node(state: State):
    print(">>> travel_node")
    writer = get_stream_writer()
    writer({"node", ">>> travel_node"})
    return {
        "messages": [HumanMessage(content="travel_node")],
        "type": "travel",
    }


def joke_node(state: State):
    print(">>> joke_node")
    writer = get_stream_writer()
    writer({"node", ">>> joke_node"})

    system_prompt = """你是一个笑话大师，根据用户的问题写一个笑话，100字以内。"""
    prompts = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": state["messages"][0]},
    ]
    response = llm.invoke(prompts)
    writer({"joke_node response": response.content})
    return {
        "messages": [response.content],
        "type": "joke",
    }


def couplet_node(state: State):
    print(">>> couplet_node")
    writer = get_stream_writer()
    writer({"node", ">>> couplet_node"})
    return {
        "messages": [HumanMessage(content="couplet_node")],
        "type": "couplet",
    }


# 条件路由
def routing_func(state: State):
    if state["type"] == "travel":
        return "travel_node"
    elif state["type"] == "joke":
        return "joke_node"
    elif state["type"] == "couplet":
        return "couplet_node"
    elif state["type"] == END:
        return END
    else:
        return "other_node"


# 构建图
builder = StateGraph(State)

# 添加节点
builder.add_node("supervisor_node", supervisor_node)
builder.add_node("travel_node", travel_node)
builder.add_node("joke_node", joke_node)
builder.add_node("couplet_node", couplet_node)
builder.add_node("other_node", other_node)

# 添加Edge边
builder.add_edge(START, "supervisor_node")
builder.add_conditional_edges("supervisor_node", routing_func, ["travel_node", "joke_node", "couplet_node", "other_node", END])  # 条件Edge,每个节点
builder.add_edge("travel_node", "supervisor_node")
builder.add_edge("joke_node", "supervisor_node")
builder.add_edge("couplet_node", "supervisor_node")
builder.add_edge("other_node", "supervisor_node")

# 构建Graph
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

if __name__ == '__main__':
    config = {
        "configurable": {
            "thread_id": "1"
        },
    }

    input_messages = {
        "messages": ["给我讲一个郭德纲的笑话"],
        # "messages": ["今天天气怎么样"],
    }

    for chunk in graph.stream(input_messages, config, stream_mode="custom"):  # custom,values
        print(chunk)

    # res = graph.invoke(input_messages, config, stream_mode="values")
    # print(res["messages"][-1].content)
