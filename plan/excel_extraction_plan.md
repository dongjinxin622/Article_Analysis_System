# 计划：v2 "Excel 题录数据批量提取" 功能移植到 v3（LLM 嵌入式智能对话模式）

## Context

v2 有一个完整的 Excel 题录数据批量提取功能，基于 LangGraph + LangChain 实现。v3 缺少此功能。

**v2 的 HITL 是机械式的按钮交互**：用户只能点击预设按钮（continue/modify/terminate），无法表达更复杂的意图。

**本方案引入 LLM 嵌入式对话**：
- 用户可以用自然语言与系统对话
- LLM 理解用户意图，转化为系统动作
- 非预期输入时，LLM 智能解释问题并提供引导
- 类似 ChatGPT 风格的交互体验

---

## 核心创新：LLM 嵌入式智能 HITL

### 传统 HITL vs 智能 HITL

```
传统机械式 HITL：
┌─────────────────────────────┐
│ 字段检查未通过              │
│ 缺少 DOI 字段               │
│                             │
│ [继续] [修改] [终止]        │ ← 用户只能选按钮
└─────────────────────────────┘

智能对话式 HITL：
┌─────────────────────────────┐
│ 🤖 AI助手:                  │
│ 我注意到有 15 条记录缺少 DOI │
│ 字段，这可能会影响后续处理。│
│                             │
│ 您可以：                    │
│ 1. 忽略这些记录继续处理     │
│ 2. 手动补充 DOI             │
│ 3. 调低 DOI 为非必填字段    │
│                             │
│ 请告诉我您想怎么处理？      │
└─────────────────────────────┐
│ 👤 用户输入:                │
│ 那些记录是什么类型的论文？  │ ← 用户自由提问
│                             │
└─────────────────────────────┐
│ 🤖 AI助手:                  │
│ 我查了一下，这 15 条主要是  │
│ 会议论文，DOI 可选。建议    │
│ 将 DOI 改为非必填。         │
│ 您同意吗？                  │
└─────────────────────────────┐
│ 👤 用户输入:                │
│ 好的，继续处理              │ ← 自然语言表达意图
└─────────────────────────────┘
```

### LLM 对话节点设计

```python
async def llm_hitl_node(state: Dict, hitl_ctx: WebHITLContext) -> Dict:
    """LLM 嵌入式智能 HITL 节点"""

    # 1. 构建对话上下文
    context = build_hitl_context(state)  # 当前检查问题 + 数据详情

    # 2. 调用 LLM 生成智能回复
    llm_response = await call_conversation_llm(
        system_prompt=HITL_SYSTEM_PROMPT,
        user_message=None,  # 首次进入，LLM 主动发起
        context=context
    )

    # 3. 发送给用户，等待回复
    await hitl_ctx.send_message({
        "type": "llm_chat",
        "content": {
            "role": "assistant",
            "message": llm_response,
            "suggested_actions": extract_suggested_actions(llm_response)
        }
    })

    # 4. 等待用户输入（可能是自然语言，也可能是按钮）
    user_input = await hitl_ctx.wait_for_user_input()

    # 5. 如果是自然语言，LLM 解析意图
    if user_input.get("type") == "text":
        intent = await parse_user_intent(
            user_message=user_input["text"],
            context=context,
            available_actions=["continue", "modify", "terminate", "retry"]
        )
        action = intent["action"]
        action_data = intent["data"]  # 可能包含用户补充的数据
    else:
        action = user_input.get("action", "continue")

    return {
        "user_action": action,
        "action_data": action_data,
        "chat_history": state.get("chat_history", []) + [
            {"role": "assistant", "content": llm_response},
            {"role": "user", "content": user_input.get("text", action)}
        ]
    }
```

### HITL 对话系统提示词

```python
HITL_SYSTEM_PROMPT = """
你是批量数据处理任务的智能助手。你的职责是：
1. 用清晰友好的语言向用户解释当前遇到的问题
2. 提供多个处理方案供用户选择
3. 回答用户关于数据的任何问题
4. 将用户的自然语言回复转化为系统可执行的动作

当前检查类型：{check_type}
问题描述：{error_message}
影响范围：{affected_count} 条记录
可选动作：{available_actions}

回复格式：
- 用自然语言解释问题
- 列出建议的处理方案
- 结尾询问用户意图
- 如果用户回复不是标准动作，解析其真实意图并给出建议

示例回复：
"我发现有 23 条记录的摘要字段为空。这会导致 LLM 评估时信息不足。
您可以选择：
1. 【继续处理】 - 接受当前数据，摘要缺失的记录评估结果可能不准确
2. 【调整阈值】 - 将摘要改为非必填字段
3. 【手动补充】 - 我可以帮您定位这些记录，您手动补充摘要

请问您想怎么处理？"
"""
```

### 用户意图解析

```python
async def parse_user_intent(
    user_message: str,
    context: Dict,
    available_actions: List[str]
) -> Dict:
    """LLM 解析用户自然语言意图"""

    parse_prompt = f"""
用户输入："{user_message}"

可选动作：{available_actions}

请分析用户意图，返回 JSON：
{
    "action": "continue/modify/terminate/retry/ask_more",
    "data": { ... },  // 如果用户提供了补充数据
    "confidence": 0.0-1.0,
    "reasoning": "解析理由"
}

如果用户在提问而非做决定，返回 "ask_more"。
如果意图不明确，返回置信度较低的推测。
"""

    response = await llm.chat(parse_prompt, json_mode=True)
    return parse_json(response)
```

---

## LangGraph 工作流更新

### 新增对话节点

```python
# 原有节点保持不变，但 HITL 节点改为智能对话版本
WEB_NODES = {
    # 智能对话 HITL 节点（替代原有机械按钮节点）
    "llm_hitl_node": llm_hitl_node,           # 通用智能 HITL
    "llm_prompt_check_node": llm_prompt_check_node,  # Prompt 确认对话
    "llm_eval_approval_node": llm_eval_approval_node,  # 评估结果确认对话

    # 辅助节点
    "ask_more_node": ask_more_node,           # 用户提问处理
    "data_lookup_node": data_lookup_node,     # 数据查询（回答用户问题）
}

# 工作流中替换
workflow.add_node("human_approval", WEB_NODES["llm_hitl_node"])
workflow.add_node("prompt_check", WEB_NODES["llm_prompt_check_node"])
workflow.add_node("eval_approval", WEB_NODES["llm_eval_approval_node"])
```

### 条件边路由支持对话意图

```python
def llm_hitl_router(state: AgentState) -> str:
    """基于 LLM 解析的意图路由"""

    action = state.get("user_action", "continue")
    action_data = state.get("action_data", {})

    # ask_more 表示用户在提问，不做出决定
    if action == "ask_more":
        return "data_lookup"  # 进入数据查询节点，回答用户问题

    if action == "terminate":
        return "terminate"

    if action == "modify":
        # action_data 可能包含具体的修改内容
        if action_data.get("threshold"):
            state["config"]["min_quality_score"] = action_data["threshold"]
        if action_data.get("required_fields"):
            state["config"]["required_fields"] = action_data["required_fields"]
        return "modify_config"

    # continue / accept
    pending = state.get("pending_check", "")
    next_map = {
        "field": "data_quality",
        "quality": "filter",
        "filter": "parse_strategy",
        "prompt": "prepare_eval",
        "eval": "export_result"
    }
    return next_map.get(pending, "integrate")
```

### 数据查询节点（回答用户问题）

```python
async def data_lookup_node(state: Dict, hitl_ctx: WebHITLContext) -> Dict:
    """回答用户关于数据的问题"""

    user_question = state.get("action_data", {}).get("question", "")
    df = state.get("df")

    # 根据问题类型查询数据
    if "哪些记录" in user_question or "什么类型" in user_question:
        # 查询受影响的记录详情
        affected = get_affected_records(df, state["pending_check"])
        answer = f"受影响的记录共 {len(affected)} 条：\n"
        for i, row in affected[:10].iterrows():
            answer += f"- {row.get('title', 'N/A')[:50]}...\n"
        if len(affected) > 10:
            answer += f"（还有 {len(affected)-10} 条...）"

    elif "统计" in user_question or "比例" in user_question:
        # 统计分析
        stats = analyze_affected_records(df, state["pending_check"])
        answer = f"统计分析：\n{format_stats(stats)}"

    else:
        # 通用 LLM 回答
        answer = await llm.answer_data_question(user_question, df)

    # 发送回答，继续等待用户决定
    await hitl_ctx.send_message({
        "type": "llm_chat",
        "content": {"role": "assistant", "message": answer}
    })

    # 继续等待用户输入
    user_input = await hitl_ctx.wait_for_user_input()

    return {
        "user_action": parse_intent_from_input(user_input),
        "action_data": user_input.get("data", {}),
        # 不改变 pending_check，等待用户做出决定
    }
```

---

## 前端智能对话组件

### Chat 风格对话框

```vue
<template>
  <el-dialog
    v-model="chatDialogVisible"
    title="AI助手对话"
    width="700px"
    class="hitl-chat-dialog"
    :close-on-click-modal="false"
  >
    <!-- 对话历史 -->
    <div class="chat-messages">
      <div v-for="msg in chatHistory" :class="['chat-message', msg.role]">
        <div class="message-avatar">
          <span v-if="msg.role === 'assistant'">🤖</span>
          <span v-else>👤</span>
        </div>
        <div class="message-content">
          <markdown-render :content="msg.content" />
        </div>
      </div>

      <!-- 当前问题详情 -->
      <div v-if="currentIssue" class="issue-details">
        <el-alert :type="issueType" :closable="false">
          <template #title>{{ currentIssue.summary }}</template>
          {{ currentIssue.details }}
        </el-alert>
      </div>
    </div>

    <!-- 建议动作按钮 -->
    <div v-if="suggestedActions.length" class="suggested-actions">
      <el-button
        v-for="action in suggestedActions"
        :type="action.type"
        @click="quickAction(action.value)"
      >
        {{ action.label }}
      </el-button>
    </div>

    <!-- 用户输入 -->
    <div class="chat-input">
      <el-input
        v-model="userInput"
        type="textarea"
        :rows="2"
        placeholder="输入您的回复或问题..."
        @keydown.enter.ctrl="sendMessage"
      />
      <el-button type="primary" @click="sendMessage">发送</el-button>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useExcelExtractionWs } from '@/composables/useExcelExtractionWs'

const { sendAction, sendTextMessage } = useExcelExtractionWs()

const chatHistory = ref([])
const userInput = ref('')
const suggestedActions = ref([])
const currentIssue = ref(null)

// WebSocket 收到 llm_chat 消息时
function onLLMChat(data) {
  chatHistory.value.push({
    role: 'assistant',
    content: data.message
  })
  suggestedActions.value = data.suggested_actions || []
  currentIssue.value = data.issue_details || null
}

// 发送文本消息
function sendMessage() {
  if (!userInput.value.trim()) return

  chatHistory.value.push({
    role: 'user',
    content: userInput.value
  })

  sendTextMessage(userInput.value)
  userInput.value = ''
}

// 快捷按钮
function quickAction(action) {
  sendAction(action)
}
</script>
```

### WebSocket 消息处理扩展

```typescript
// 新增消息类型
interface LLMChatMessage {
  type: 'llm_chat'
  content: {
    role: 'assistant'
    message: string  // LLM 生成的回复（Markdown格式）
    suggested_actions: SuggestedAction[]  // 建议的快捷按钮
    issue_details: IssueDetails | null  // 当前问题的详细描述
  }
}

interface UserInputMessage {
  type: 'user_input'
  content: {
    input_type: 'text' | 'action'  // 文本输入 或 按钮点击
    text?: string  // 文本内容
    action?: string  // 选择的动作
    data?: any  // 附加数据
  }
}

// WebSocket 发送方法
class ExcelExtractionWebSocket {
  // 发送文本消息
  sendTextMessage(text: string) {
    this.socket.emit('user_input', {
      input_type: 'text',
      text: text
    })
  }

  // 发送快捷动作
  sendAction(action: string, data?: any) {
    this.socket.emit('user_input', {
      input_type: 'action',
      action: action,
      data: data
    })
  }
}
```

---

## 对话场景示例

### 场景1：字段检查失败

```
🤖 AI助手:
我检查了您上传的数据，发现以下问题：

📊 字段完整性分析
- DOI: 缺失 15 条 (8.2%)
- Title: 全部存在 ✓
- Abstract: 缺失 3 条 (1.6%)

缺少 DOI 的记录主要是会议论文，DOI 字段对这类论文通常是可选的。

您可以选择：
1. 【继续处理】 - 接受当前数据质量
2. 【降低要求】 - 将 DOI 改为非必填字段
3. 【查看详情】 - 查看具体哪些记录缺少 DOI

请问您想如何处理？

[继续处理] [降低要求] [查看详情]

👤 用户输入: 那些缺少DOI的记录是什么期刊的？

🤖 AI助手:
让我查询一下...

缺少 DOI 的 15 条记录来源分布：
- IEEE Conference: 8 条
- ACM Conference: 4 条
- 国内会议: 3 条

这些都是会议论文，DOI 获取率较低是正常的。建议您选择"降低要求"继续处理。

[降低要求] [继续处理] [查看这些记录]

👤 用户输入: 好的，降低DOI的必填要求

🤖 AI助手:
已将 DOI 字段改为非必填。继续进行数据质量检查...

✓ 字段检查通过，进入下一步
```

### 场景2：Prompt 确认

```
🤖 AI助手:
根据您上传的策略文档，我生成了以下提取 Prompt：

📝 提取字段定义
- related: 是否与激光加工领域相关
- institution: 通讯作者所属机构
- summary: 论文核心贡献摘要（200字）
- laser_type: 激光器类型（领域特定）
- pulse_width: 脉冲宽度指标（领域特定）

完整 Prompt 如下：
---
{generated_prompt}
---

您可以：
1. 【接受】 - 使用此 Prompt 开始评估
2. 【编辑】 - 手动修改 Prompt 内容
3. 【重新生成】 - 我重新生成一个版本
4. 【使用默认】 - 使用系统默认 Prompt

请问您的选择？

[接受] [编辑] [重新生成] [使用默认]

👤 用户输入: laser_type这个字段的定义不太准确，能改成激光加工类型吗？

🤖 AI助手:
好的，我理解您的意思。您希望将"激光器类型"改为更广义的"激光加工类型"，包括切割、焊接、打标等工艺类型。

我来更新 Prompt...

已更新字段定义：
- laser_type → laser_process_type: 激光加工类型（切割/焊接/打标/熔覆等）

更新后的 Prompt 已保存。您确认使用这个版本吗？

[确认使用] [继续编辑] [预览完整Prompt]
```

---

## 后端核心组件

### 对话上下文构建

```python
def build_hitl_context(state: Dict) -> Dict:
    """构建 HITL 对话上下文"""

    pending = state.get("pending_check", "unknown")
    check_result = state.get("check_results", {}).get(pending, {})
    df = state.get("df")

    context = {
        "check_type": pending,
        "error_message": state.get("error_message", ""),
        "affected_count": check_result.get("failed_count", 0),
        "total_count": len(df) if df is not None else 0,
        "available_actions": get_available_actions(pending),
        "data_preview": None,
    }

    # 添加受影响记录的预览
    if df is not None and check_result.get("failed_indices"):
        failed_rows = df.iloc[check_result["failed_indices"]]
        context["data_preview"] = failed_rows.head(10).to_dict(orient="records")

    return context
```

### LLM 对话服务

```python
class HITLConversationLLM:
    """HITL 对话 LLM 服务"""

    def __init__(self, model: str = "qwen-plus"):
        self.llm = ChatOpenAI(model=model, temperature=0.7)

    async def chat(self, context: Dict, user_message: str = None) -> str:
        """生成对话回复"""

        system_prompt = HITL_SYSTEM_PROMPT.format(**context)

        messages = [
            SystemMessage(content=system_prompt),
        ]

        # 添加历史对话
        for msg in context.get("chat_history", []):
            if msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
            else:
                messages.append(HumanMessage(content=msg["content"]))

        # 添加当前用户消息
        if user_message:
            messages.append(HumanMessage(content=user_message))

        response = await self.llm.ainvoke(messages)
        return response.content

    async def parse_intent(self, user_message: str, context: Dict) -> Dict:
        """解析用户意图"""

        parse_prompt = f"""
用户输入："{user_message}"
可选动作：{context['available_actions']}
当前检查类型：{context['check_type']}

请判断用户的真实意图，返回 JSON：
{
    "action": "continue|modify|terminate|retry|ask_more",
    "data": {},  // 用户提供的补充数据（如新的阈值、字段列表等）
    "confidence": 0.0-1.0,
    "reasoning": "为什么这样判断"
}

注意：
- 如果用户在提问或想要更多信息，返回 "ask_more"
- 如果用户说"好的"、"同意"、"可以"，理解为 "continue"
- 如果用户提出具体修改，将修改内容放入 data
"""

        response = await self.llm.ainvoke([
            SystemMessage(content=parse_prompt),
            HumanMessage(content=user_message)
        ])

        return parse_json_response(response.content)
```

---

## 完整工作流图

```
START
  │
  ▼
load_config ──────────────────────────────► integrate
                                            │
                                            ▼
                                       field_check
                                            │
                                   ┌────────┴────────┐
                                   │                 │
                            [passed]            [failed]
                                   │                 │
                                   ▼                 ▼
                             data_quality     llm_hitl ◄──┐
                                   │                 │    │
                          ┌────────┴────────┐   ┌────┴────┴──┐
                          │                 │   │             │
                   [passed]            [failed] │ ask_more    │
                          │                 │   │             │
                          ▼                 ▼   ▼             │
                        filter        ◄─────► data_lookup ───┤
                          │                      │           │
                 ┌────────┴────────┐             │           │
                 │                 │             │           │
          [passed]            [failed]           │           │
                 │                 │             │           │
                 ▼                 ▼             │           │
           parse_strategy ◄── llm_hitl ◄─────────┴───────────┘
                 │
                 ▼
          generate_prompt
                 │
                 ▼
           llm_prompt_check ◄──► edit_prompt ◄──► manual_prompt
                 │                    │                  │
                 │                    ▼                  ▼
                 └─────────────────► prepare_eval ◄─────┘
                                      │
                                      ▼
                                  batch_eval
                                      │
                                      ▼
                                 result_check
                                      │
                             ┌────────┴────────┐
                             │                 │
                      [passed]            [failed]
                             │                 │
                             ▼                 ▼
                       export_result      llm_eval_approval ◄──┐
                             │                      │          │
                             ▼               ┌──────┴──────┐   │
                            END              │             │   │
                                    retry ◄──┤ ask_more    │   │
                                      │      │             │   │
                                      │      ▼             │   │
                                      │  data_lookup ──────┴───┘
                                      │      │
                                      └──────┴──► batch_eval (重试)
```

---

## 文件清单

### 后端（新增对话模块）

| 文件 | 操作 | 内容 |
|------|------|------|
| `backend/app/models/excel_extraction.py` | 新建 | 数据库模型 |
| `backend/app/schemas/excel_extraction.py` | 新建 | Schema定义 |
| `backend/app/excel_extraction/state.py` | 新建 | AgentState TypedDict |
| `backend/app/excel_extraction/nodes.py` | 新建 | 同步处理节点 |
| `backend/app/excel_extraction/llm_hitl_nodes.py` | 新建 | **智能对话 HITL 节点** |
| `backend/app/excel_extraction/conversation.py` | 新建 | **HITLConversationLLM 服务** |
| `backend/app/excel_extraction/agent.py` | 新建 | WebAgentRunner + 工作流构建 |
| `backend/app/excel_extraction/models.py` | 新建 | 动态Pydantic模型 |
| `backend/app/api/v1/excel_extraction.py` | 新建 | API + WebSocket路由 |
| `backend/app/main.py` | 修改 | 注册路由 |
| `backend/requirements.txt` | 修改 | 添加依赖 |

### 前端（新增对话组件）

| 文件 | 操作 | 内容 |
|------|------|------|
| `frontend/src/types/excel_extraction.ts` | 新建 | 类型定义 |
| `frontend/src/api/excel_extraction.ts` | 新建 | API封装 |
| `frontend/src/composables/useExcelExtractionWs.ts` | 新建 | WebSocket连接管理 |
| `frontend/src/components/HITLChatDialog.vue` | 新建 | **智能对话弹窗组件** |
| `frontend/src/views/BatchExtraction.vue` | 修改 | 添加Tab + 集成对话组件 |

---

## 需新增依赖

```
langgraph>=0.2.0
langchain-openai>=0.3.0
python-docx>=1.1.0
```

---

## 实现顺序

### 阶段1：基础结构
1. 数据库模型 + Schema
2. State 定义 + 动态模型生成

### 阶段2：处理节点
3. 同步处理节点（数据整合/检查/Prompt生成/批量评估）
4. 导出节点

### 阶段3：智能对话核心
5. **HITLConversationLLM 服务**（对话 + 意图解析）
6. **智能 HITL 节点**（llm_hitl_node + data_lookup_node）
7. **对话上下文构建**

### 阶段4：工作流集成
8. WebAgentRunner + 工作流构建
9. 条件边路由（支持 ask_more 路径）

### 阶段5：API + WebSocket
10. API 路由 + WebSocket 端点
11. 消息类型处理（llm_chat / user_input）

### 阶段6：前端
12. WebSocket 连接管理
13. **智能对话弹窗组件**（ChatGPT风格）
14. 批量提取页面 Tab 集成

---

## 验证场景

1. **字段检查失败 → 用户提问 → 查看详情 → 继续处理**
2. **Prompt 确认 → 用户提出修改 → LLM理解意图 → 更新Prompt**
3. **评估结果失败 → 用户询问失败原因 → LLM解释 → 决定重试**
4. **用户输入模糊语言 → LLM解析意图 → 给出建议**
5. **用户输入完全无关内容 → LLM友好引导回正题**

---

## 实现状态（2026-04-22）

### 后端测试结果

```
✅ Models 导入成功
✅ State 导入成功
✅ 动态模型生成成功
✅ Conversation 服务导入成功
✅ Nodes 导入成功 (13 个节点)
✅ Agent 导入成功
✅ API 路由导入成功 (9 个端点)
✅ Main app 导入成功
✅ Schema 导入成功
```

### 已创建文件

**后端（10 文件新建，3 文件修改）**
- `backend/app/models/excel_extraction.py` ✅
- `backend/app/models/__init__.py` ✅（修改）
- `backend/app/schemas/excel_extraction.py` ✅
- `backend/app/excel_extraction/__init__.py` ✅
- `backend/app/excel_extraction/state.py` ✅
- `backend/app/excel_extraction/models.py` ✅（修复 Dict 导入）
- `backend/app/excel_extraction/nodes.py` ✅
- `backend/app/excel_extraction/conversation.py` ✅
- `backend/app/excel_extraction/llm_hitl_nodes.py` ✅
- `backend/app/excel_extraction/agent.py` ✅
- `backend/app/api/v1/excel_extraction.py` ✅
- `backend/app/main.py` ✅（修改）
- `backend/requirements.txt` ✅（修改）

**前端（5 文件新建，1 文件修改）**
- `frontend/src/types/excel_extraction.ts` ✅
- `frontend/src/api/excel_extraction.ts` ✅
- `frontend/src/composables/useExcelExtractionWs.ts` ✅
- `frontend/src/components/HITLChatDialog.vue` ✅
- `frontend/src/components/ExcelExtractionTab.vue` ✅
- `frontend/src/views/BatchExtraction.vue` ✅（修改）

### 待完成

1. **安装依赖**：`pip install langgraph langchain-openai python-docx`
2. **数据库表创建**：重启后端自动创建
3. **前端依赖**：确保 `marked` 和 `socket.io-client` 已安装
4. **端到端测试**：上传 Excel 文件验证完整流程

---

## 技术细节

### 1. 对话历史管理

```python
# State 中添加对话历史
class AgentState(TypedDict):
    ...
    chat_history: List[Dict]  # [{"role": "assistant/user", "content": "..."}]
    hitl_turns: int  # 当前 HITL 轮次计数（防止无限对话）

# 每次对话后追加
state["chat_history"].append({"role": "user", "content": user_input})
state["chat_history"].append({"role": "assistant", "content": llm_response})
state["hitl_turns"] += 1

# 设置上限，防止用户无限对话
if state["hitl_turns"] > 10:
    # 强制引导用户做出决定
    llm_response = await llm.force_decision_prompt(state)
```

### 2. Markdown 渲染

前端使用 `md-editor-v3` 或 `vue-markdown-render` 渲染 LLM 回复：

```vue
<template>
  <MdPreview :modelValue="msg.content" />
</template>
```

### 3. 流式响应（可选增强）

```python
async def stream_chat_response(context: Dict):
    """流式生成对话回复"""
    async for chunk in llm.astream(messages):
        await hitl_ctx.send_message({
            "type": "llm_chat_stream",
            "content": {"chunk": chunk.content}
        })
```

---

## 与 v2 的主要区别

| 特性 | v2（机械式） | v3（智能式） |
|------|-------------|-------------|
| HITL交互 | 按钮选择 | 自然语言对话 |
| 用户提问 | 无法处理 | LLM回答+数据查询 |
| 意图解析 | 预定义按钮 | LLM语义理解 |
| 问题解释 | 固定文本 | LLM动态生成 |
| 修改建议 | 用户手动 | LLM智能建议 |
| 非预期输入 | 按钮不响应 | LLM引导处理 |
| 对话历史 | 无 | 上下文连贯 |