# -*- coding: utf-8 -*-
# @Time    : 2026/2/16 20:14
# @Author  : yangyuexiong
# @Email   : yang6333yyx@126.com
# @File    : test_llm.py
# @Software: PyCharm

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key="sk-10dda2d7b42847a49e6e78d94e3eab33",
    base_url="https://api.deepseek.com",
    temperature=0.2
)

# resp = llm.invoke("用一句话解释什么是 FastAPI")
# print(resp.content)

agent = create_agent(model=llm, tools=[])
messages_list = {
    "messages": [
        {"role": "user", "content": "用一句话解释什么是 FastAPI"}
        # ("user", "用一句话解释什么是 FastAPI")
    ]
}
resp = agent.invoke(messages_list)
print(resp)
print(resp.keys())
print(resp["messages"][-1])

if __name__ == '__main__':
    pass
