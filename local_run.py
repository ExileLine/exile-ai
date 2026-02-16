# -*- coding: utf-8 -*-
# @Time    : 2026/2/13 22:34
# @Author  : yangyuexiong
# @Email   : yang6333yyx@126.com
# @File    : local_run.py
# @Software: PyCharm


import uvicorn

if __name__ == '__main__':
    uvicorn.run("app.main:app", host="0.0.0.0", port=7769, reload=True)
