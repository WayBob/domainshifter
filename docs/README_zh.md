# DomainShifter - 多天气风格转换自动化平台

> [English Documentation](../README.md) | [日本語ドキュメント](./README_ja.md)

一个智能自动化平台，利用多个模型上下文协议（MCP）服务器实现无缝的多天气域转换和神经风格转换工作流。具备强大的代理功能和全面的自检能力。

## 概述

DomainShifter是一个专为**多天气域转换和神经风格转换**操作设计的专业自动化平台。通过不同传输协议（stdio和HTTP）集成多个MCP服务器，实现基于天气的无缝域适应和艺术风格转换工作流。

### 核心使命
在不同天气域（晴天 ↔ 雨天 ↔ 雪天 ↔ 雾天）之间转换视觉内容，同时通过先进的神经风格转换技术保持语义一致性和艺术质量。

### 天气域转换
- **自动天气检测**: 智能识别输入图像中的天气条件
- **多域适应**: 不同天气场景之间的无缝转换
- **风格感知转换**: 跨天气域的上下文保持神经风格转换
- **批量处理**: 高效处理大规模天气域转换任务

![DomainShifter概览](../domainshifter_overview.png)

## 核心特性

### 天气域转换引擎
- **晴天到X转换**: 将晴天场景转换为雨天、雪天或雾天条件
- **雨效合成**: 逼真的雨效生成，包含正确的光照和反射
- **雪效生成**: 自然的雪覆盖效果，具有深度和大气效果
- **雾效模拟**: 基于距离可见度的大气雾效渲染
- **双向转换**: 支持任意天气域之间的转换

### 神经风格转换集成
- **艺术风格适应**: 在保持天气特征的同时应用艺术风格
- **天气感知风格化**: 尊重天气特定光照和大气效果的风格转换
- **GPU加速处理**: 在远程GPU集群上进行高性能神经网络推理
- **多分辨率支持**: 处理从缩略图到高分辨率格式的图像

### 多传输协议MCP集成
- **本地服务器**: 通过stdio传输协议连接本地MCP服务器
- **远程GPU服务**: 通过HTTP连接远程GPU驱动的风格转换服务器
- **统一接口**: 单一`MultiServerMCPClient`处理所有连接类型
- **优雅降级**: 当服务器不可用时自动回退

### 智能代理系统
- **ReAct代理**: 具有推理和行动能力的交互式代理，用于复杂工作流
- **结构化数据处理**: 使用Pydantic模型进行类型安全的天气和风格元数据处理
- **LLM驱动解析**: 自动将非结构化工具输出转换为结构化数据
- **强大错误处理**: 即使某些服务失败也能继续执行

### 自检与诊断
- **启动验证**: 自动验证所有配置的MCP服务器
- **健康监控**: 实时状态检查和详细报告
- **回退策略**: 主服务不可用时智能选择工具

### 灵活的LLM支持
- **多提供商**: 支持OpenAI、Anthropic、Google、DeepSeek和XAI模型
- **动态模型切换**: 运行时更改模型
- **配置驱动**: 基于JSON的模型和服务器配置

## 架构

### 核心组件

- **`mcp_client_manager.py`**: 具有回退机制的强大MCP客户端
- **`llm_manager.py`**: 支持多提供商的统一LLM接口

- **`run_agent.py`**: 具有自检功能的交互式ReAct代理

### MCP服务器结构

本地MCP服务器遵循结构化包布局：
```
mcp_servers/
├── general/
│   ├── __init__.py
│   ├── __main__.py
│   └── server.py
└── remote_file_explorer/
    ├── __init__.py
    ├── __main__.py
    └── server.py
```

### 配置文件

- **`mcp.json`**: MCP服务器配置（stdio和HTTP传输）
- **`models.json`**: 可用LLM模型及其标识符
- **`.env`**: API密钥和环境变量

## 使用方法

### 前置要求

```bash
# 使用uv安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate
```



### 交互式代理模式

启动与ReAct代理的交互式聊天会话：

```bash
python run_agent.py
```

代理将：
1. 对所有配置的MCP服务器执行自检
2. 报告连接状态和可用工具
3. 进入用户查询的交互模式

### 配置

#### MCP服务器 (`mcp.json`)
```json
{
  "mcpServers": {
    "local-server": {
      "command": "{PROJECT_ROOT}/.venv/bin/python",
      "args": ["-m", "domainshifter.mcp_servers.general"],
      "transport": "stdio"
    },
    "remote-service": {
      "url": "http://remote-host:3000/mcp",
      "transport": "streamable_http"
    }
  }
}
```

#### 模型 (`models.json`)
```json
[
  {
    "name": "Claude Sonnet 4",
    "id": "claude-sonnet-4-20250514"
  },
  {
    "name": "GPT-4o",
    "id": "gpt-4o"
  }
]
```

## 远程GPU服务

平台利用专用的GPU驱动远程服务进行密集计算任务：

### 天气域转换服务
- **天气转换引擎**: 高性能天气域转换
- **风格转换集群**: 分布式神经风格转换处理
- **批处理管道**: 大型图像数据集的可扩展处理
- **实时监控**: 实时状态和性能指标

### 服务基础设施
- **GPU加速**: 针对实时处理的CUDA优化推理
- **Tailscale网络**: 安全的跨网络连接
- **负载均衡**: 在可用GPU节点间自动分配
- **自动扩展**: 基于工作负载的动态资源分配

### 专业服务
- **LocalWeatherService**: 实时天气数据集成，用于上下文感知处理
- **StyleTransferService**: 具有天气保持功能的高级神经风格转换
- **SnowGenerationService**: 专业的雪效合成和应用

> **注意**: 这些GPU驱动的服务实现了实时天气域转换和风格转换操作，这些操作在本地硬件上计算量很大。

## 错误处理与鲁棒性

- **连接超时**: 可配置超时防止在不可用服务上挂起
- **优雅降级**: 系统在可用服务器上继续运行
- **回退工具**: 主工具失败时自动选择替代工具
- **全面日志**: 详细状态报告用于调试

## 开发

### 虚拟环境管理
```bash
# 创建虚拟环境
uv venv

# 安装依赖
uv sync

# 添加新包
uv add package-name
```

### 测试MCP服务器
```bash
# 测试单个MCP服务器
python -m domainshifter.mcp_servers.general

# 测试客户端连接
python mcp_client_manager.py
```

## 许可证

本项目采用MIT许可证。

---

---

**DomainShifter** - 通过智能自动化连接天气域

[English Documentation](../README.md) | [日本語ドキュメント](./README_ja.md)