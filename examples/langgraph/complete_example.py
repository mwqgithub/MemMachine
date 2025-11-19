"""
完整的 LangGraph + MemMachine 集成示例

这个文件包含一个可以直接运行的完整示例，展示了如何在 LangGraph 中使用 MemMachine。
"""

import os
import sys
from typing import Annotated, TypedDict

# 添加项目根目录到路径，以便导入模块
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, project_root)

from langgraph.graph import END, StateGraph

# 导入工具（从当前目录）
try:
    from tool import MemMachineTools, create_add_memory_tool, create_search_memory_tool
except ImportError:
    # 如果从项目根目录运行，使用完整路径
    from examples.langgraph.tool import (
        MemMachineTools,
        create_add_memory_tool,
        create_search_memory_tool,
    )

# ============================================================================
# 配置
# ============================================================================
MEMORY_BACKEND_URL = os.getenv("MEMORY_BACKEND_URL", "http://localhost:8080")
ORG_ID = os.getenv("LANGGRAPH_ORG_ID", "langgraph_org")
PROJECT_ID = os.getenv("LANGGRAPH_PROJECT_ID", "langgraph_project")
GROUP_ID = os.getenv("LANGGRAPH_GROUP_ID", "langgraph_demo")
AGENT_ID = os.getenv("LANGGRAPH_AGENT_ID", "demo_agent")
USER_ID = os.getenv("LANGGRAPH_USER_ID", "demo_user")
SESSION_ID = os.getenv("LANGGRAPH_SESSION_ID", "demo_session_001")


# ============================================================================
# 状态定义
# ============================================================================
class AgentState(TypedDict):
    """Agent 工作流的状态定义"""

    messages: Annotated[list, "对话消息列表"]
    user_id: str
    context: str
    memory_tool_results: Annotated[list, "记忆工具调用的结果"]


# ============================================================================
# 初始化 MemMachine 工具
# ============================================================================
print("初始化 MemMachine 工具...")
tools = MemMachineTools(
    base_url=MEMORY_BACKEND_URL,
    org_id=ORG_ID,
    project_id=PROJECT_ID,
    group_id=GROUP_ID,
    agent_id=AGENT_ID,
    user_id=USER_ID,
    session_id=SESSION_ID,
)

# 服务器连接会在第一次使用时自动检查
print(f"✅ MemMachine 工具已初始化，服务器地址: {MEMORY_BACKEND_URL}")

# 创建工具函数
add_memory = create_add_memory_tool(tools)
search_memory = create_search_memory_tool(tools)


# ============================================================================
# 定义 LangGraph 节点
# ============================================================================
def memory_node(state: AgentState):
    """
    记忆节点：搜索相关记忆并添加新记忆
    """
    # 获取最后一条消息的内容
    # 注意：messages 可能是字典或对象，需要处理两种情况
    if not state["messages"]:
        return {
            "context": "",
            "memory_tool_results": [],
        }

    last_message = state["messages"][-1]
    message_content = (
        last_message.get("content")
        if isinstance(last_message, dict)
        else getattr(last_message, "content", str(last_message))
    )

    if not message_content:
        return {
            "context": "",
            "memory_tool_results": [],
        }

    # 搜索相关记忆
    search_result = search_memory(
        query=message_content,
        user_id=state["user_id"],
    )

    # 添加新记忆
    add_memory(
        content=message_content,
        user_id=state["user_id"],
    )

    return {
        "context": search_result.get("summary", ""),
        "memory_tool_results": [search_result],
    }


# ============================================================================
# 构建工作流
# ============================================================================
workflow = StateGraph(AgentState)
workflow.add_node("memory", memory_node)
workflow.set_entry_point("memory")
workflow.add_edge("memory", END)

# 编译工作流
app = workflow.compile()


# ============================================================================
# 运行示例
# ============================================================================
def main():
    """运行示例"""
    print("\n" + "=" * 60)
    print("运行 LangGraph + MemMachine 示例")
    print("=" * 60)

    # 第一次运行：添加记忆
    print("\n【步骤 1】添加第一条记忆...")
    result1 = app.invoke(
        {
            "messages": [{"content": "I like Python programming"}],
            "user_id": USER_ID,
            "context": "",
            "memory_tool_results": [],
        }
    )

    print("✅ 记忆已添加")
    print(f"   搜索到的相关记忆: {result1.get('context', '无')}")
    print(f"   记忆结果数量: {len(result1.get('memory_tool_results', []))} 条")

    # 显示详细结果
    if result1.get("memory_tool_results"):
        for mem_result in result1["memory_tool_results"]:
            if mem_result.get("status") == "success":
                results = mem_result.get("results", {})
                episodic = results.get("episodic_memory", [])
                profile = results.get("profile_memory", [])
                print(f"   - Episodic记忆: {len(episodic)} 条")
                print(f"   - Profile记忆: {len(profile)} 条")

    # 第二次运行：检索记忆
    print("\n" + "-" * 60)
    print("【步骤 2】检索记忆（测试是否能找到刚才添加的记忆）...")
    result2 = app.invoke(
        {
            "messages": [{"content": "What programming language do I like?"}],
            "user_id": USER_ID,
            "context": "",
            "memory_tool_results": [],
        }
    )

    print("✅ 记忆检索完成")
    print(f"   搜索到的相关记忆: {result2.get('context', '无')}")

    # 显示详细结果
    if result2.get("memory_tool_results"):
        for i, mem_result in enumerate(result2["memory_tool_results"], 1):
            if mem_result.get("status") == "success":
                results = mem_result.get("results", {})
                episodic = results.get("episodic_memory", [])
                profile = results.get("profile_memory", [])
                print(f"   找到 {len(episodic)} 条 Episodic 记忆")
                print(f"   找到 {len(profile)} 条 Profile 记忆")

                # 显示记忆内容
                if episodic:
                    print("\n   相关记忆内容:")
                    for j, mem in enumerate(episodic[:3], 1):  # 只显示前3条
                        content = (
                            mem.get("content", "")
                            if isinstance(mem, dict)
                            else str(mem)
                        )
                        print(f"     {j}. {content[:80]}...")

    # 第三次运行：添加更多记忆
    print("\n" + "-" * 60)
    print("【步骤 3】添加更多记忆...")
    result3 = app.invoke(
        {
            "messages": [{"content": "I also enjoy machine learning and AI"}],
            "user_id": USER_ID,
            "context": "",
            "memory_tool_results": [],
        }
    )
    print("✅ 新记忆已添加")

    # 第四次运行：综合检索
    print("\n" + "-" * 60)
    print("【步骤 4】综合检索（查找所有相关记忆）...")
    result4 = app.invoke(
        {
            "messages": [{"content": "What are my interests?"}],
            "user_id": USER_ID,
            "context": "",
            "memory_tool_results": [],
        }
    )

    print("✅ 综合检索完成")
    print(f"   搜索到的相关记忆: {result4.get('context', '无')}")

    if result4.get("memory_tool_results"):
        for mem_result in result4["memory_tool_results"]:
            if mem_result.get("status") == "success":
                results = mem_result.get("results", {})
                episodic = results.get("episodic_memory", [])
                print(f"   总共找到 {len(episodic)} 条相关记忆")

    # 清理
    tools.close()
    print("\n" + "=" * 60)
    print("✅ 示例完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
