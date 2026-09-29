---
name: kama-qa-style
description: Use when the user asks about this project's code or concepts — explaining code unit by unit, defining terms, summarizing code flow, or asking direct questions about KamaClaude.
---

# KamaClaude 问答风格

用户在这个项目里边读代码边学习，提问只有四种形式。先判断属于哪一种，再按对应格式回答。

## 一、解释代码

用户给出代码片段、函数名，或者说“从 X 开始解释”。

按执行顺序排列，每个单元一个小标题（名称 + 文件:行号），下面先一行加粗的「核心」说明它是干什么的，再跟两三条补充。

不写设计评论，不加无关章节，不重复代码里已经写明的内容。

## 二、解释专有名词

先给一句话定义，再补两三条关键点。不铺陈背景，不讲 Python 基础语法。

## 三、说明代码流程

用文字分点，1、2、3 依次说“先做什么、再做什么、得到什么”。

不用表格，不夹无关解释，不逐行复述代码。

## 四、随机提问

直接回答。问命令就给可直接复制执行的命令；问事实或行为就先跑一次，用实测结果回答。

## 通用要求

- 默认不用表格，改用文字分点
- 默认对方熟悉 Python，不讲基础语法
- 回答尽量短，先结论后补充
- 判断不出属于哪种模式时，按最接近的作答，并在开头说明按哪种模式回答
