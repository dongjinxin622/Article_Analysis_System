# V3 综合分析功能改进计划 - 参考V2深度推理模块

> **创建时间**: 2026-04-23
> **问题背景**: V3综合分析报告内容不完整，缺少V2的深度分析能力
> **参考文档**: V2项目的`deep_reasoning_service.py`和`DEEP_REASONING_ANALYSIS.md`

---

## 一、V2深度推理功能总结

### 1.1 核心架构

V2深度推理模块采用**分层架构**：
```
┌─────────────────────────────────────┐
│      Web 前端 (HTML/JS)             │
│  - deep_reasoning_comparison.html   │
│  - jc_comparison.html               │
└─────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────┐
│      API 路由层 (FastAPI)            │
│  - backend/api/deep_reasoning.py    │
│  - 8个RESTful API端点               │
└─────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────┐
│      服务层 (Service)               │
│  - deep_reasoning_service.py        │  ← 核心编排服务
│  - jc_service.py                    │  ← Jc专项服务
│  - task_manager.py                  │
│  - report_service.py                │
└─────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────┐
│   核心算法层 (deep-reasoning)       │
│  - techroute_querier.py             │  ← 技术路线构建与查询
│  - exp_scheme_retriever.py          │  ← 实验方案检索
│  - jc_index_extractor.py            │  ← Jc指标提取
│  - base_methods.py                  │  ← 向量工具+批量处理
└─────────────────────────────────────┘
```

### 1.2 三大核心分析功能

#### 功能1: 技术路线分析 (`compare_techroute`)

**输入**: NER实体 + RE关系 + 目标DOI
**输出**: 技术路线文本 + 相似论文列表（含相似度评分）

**核心流程**:
```python
DeepReasoningService.compare_techroute()
├─ Step 1: 构建技术路线
│   └─ TechRouteQuerier.process_single_ner_re()
│       ├─ 实体筛选（Manufacturing_Process_Chain、Material等）
│       ├─ 关系抽取（RE数据构建实体关系）
│       ├─ NetworkX构建有向图网络
│       └─ 生成路线文本描述 + 关键路径提取
│
├─ Step 2: 向量化
│   └─ VectorTools.text_to_vector()
│       └─ 调用LLM embedding API (text-embedding-v4, 1024维)
│
├─ Step 3: 数据库检索
│   └─ SQLite查询tech_routes表
│       ├─ 获取所有非空向量记录（排除目标DOI）
│       └─ 余弦相似度计算
│
└─ Step 4: 返回结果
    └─ 按相似度排序，返回top_k篇论文
```

**关键代码**: `_build_techroute_from_ner_re()` 方法调用 `TechRouteQuerier.process_single_ner_re()`，利用NetworkX构建技术路线网络图。

#### 功能2: 实验方案分析 (`compare_expscheme`)

**输入**: NER实体 + 目标DOI
**输出**: 8维度实验方案文本 + 相似论文列表

**8维度分类**:
| 维度 | 实体类型 | 说明 |
|------|---------|------|
| material_fabrication | Material_Fabrication | 材料准备 |
| deposition_techniques | Deposition_Techniques | 沉积技术 |
| process_parameters | Process_Parameters | 工艺参数 |
| post_processing | Post-Processing | 后处理 |
| characterization_techniques | Characterization_Techniques | 表征技术 |
| system_constraints | System_Constraints | 系统约束 |
| simulation | Simulation | 模拟分析 |
| irradiation | Irradiation | 辐照处理 |

**核心流程**:
```python
DeepReasoningService.compare_expscheme()
├─ Step 1: 生成实验方案
│   └─ ExpSchemeRetriever.process_single_ner()
│       ├─ 按8维度分类实体
│       ├─ 规则模板生成标准化文本
│       └─ 提取categories列表
│
├─ Step 2: 向量化 + 数据库检索
│
└─ Step 3: 返回结果（包含categories）
```

#### 功能3: Jc指标分析 (`JcService.extract_jc_from_excel`)

**输入**: NER实体 + Content原文 + 目标DOI
**输出**: Jc指标列表 + 条件参数 + 数据库排名

**核心流程**:
```python
JcService.extract_jc_from_excel()
├─ Step 1: 从NER提取Jc实体
│   └─ 筛选 type=Transport_Behavior, symbol=Jc/J_c
│       ├─ 提取 value, unit 字段
│       └─ 定位对应的section_idx
│
├─ Step 2: 构建 Jc→Content 映射
│   └─ _build_jc_to_content_map()
│       ├─ 按 section_idx 分组content
│       └─ 拼接同一section的段落作为原文segment
│
├─ Step 3: LLM补充条件参数
│   └─ _supplement_conditions_with_llm()
│       ├─ 检查条件完整性（温度、磁场、角度）
│       ├─ asyncio+aiohttp批量并发调用LLM
│       │   └─ max_concurrent=5, max_retry_rounds=3
│       └─ 更新缺失字段
│
├─ Step 4: 单位归一化
│   └─ _normalize_jc_unit()
│       ├─ JC_UNIT_CONVERSION映射表
│       └─ 转换为标准单位 A/cm²
│
├─ Step 5: 条件检索 + 排名计算
│   └─ filter_by_conditions()
│       ├─ 温度容差 ±5K
│       ├─ 磁场容差 ±0.5T
│       └─ 角度容差 ±5°
│   └─ rank_by_doi() 计算排名
│
└─ Step 6: 返回结果
```

### 1.3 综合分析流程

**入口**: `/api/deep-reasoning/comprehensive` POST

```python
综合分析主流程
├─ 输入来源:
│   ├─ 方式1: 上传Excel文件（包含NER+RE+content三sheet）
│   └─ 方式2: 指定result_id（从数据库加载）
│
├─ 数据加载:
│   └─ 从Excel/数据库加载 df_ner, df_re, df_content
│   └─ target_doi = 从数据中提取或用户指定
│
├─ 并行执行三大分析:
│   ├─ asyncio.gather(
│   │       compare_techroute(),
│   │       compare_expscheme(),
│   │       JcService.extract_jc_from_excel()
│   │   )
│   └─ return_exceptions=True 处理部分失败
│
├─ 综合评分计算:
│   └─ combined_score = (tech_score + exp_score) / 2
│   └─ 筛选符合阈值的结果
│
├─ LLM详细对比分析:
│   └─ _generate_llm_comparison()
│       ├─ 构建详细Prompt（包含目标论文+Top5相似论文）
│       ├─ 8维度对比分析要求
│       └─ response_format: json_object
│       └─ 返回结构化JSON报告
│
└─ 报告生成:
    ├─ Markdown报告
    ├─ Excel报告
    └─ PDF报告（可选）
```

### 1.4 LLM对比分析Prompt结构

V2的`_generate_llm_comparison()`方法构建了详细的Prompt，包含：

1. **目标论文信息**: DOI、技术路线、实验方案
2. **相似论文列表**: DOI、综合相似度、技术路线相似度、实验方案相似度、技术路线文本、实验方案文本
3. **分析维度要求**:
   - 技术路线对比
   - 实验方案对比（8个维度）
   - 关键差异总结
   - 技术趋势分析
4. **输出格式**: JSON结构，包含techroute_comparison、expscheme_comparison（8维度）、summary

### 1.5 Excel数据结构要求

V2支持上传Excel进行深度分析，Excel需包含3个sheet：

| Sheet名 | 内容 | 关键字段 |
|--------|------|---------|
| NER | 实体识别结果 | doi, section_idx, group_idx, type, subtype, symbol, value, unit, parameters |
| RE | 关系抽取结果 | doi, section_idx, group_idx, source_entity, target_entity, relation_type |
| Content | 原文段落 | doi, section_idx, paragraph_idx, text |

---

## 二、V3当前实现问题分析

### 2.1 缺失的核心功能

| 问题 | V2实现 | V3现状 |
|------|--------|--------|
| **技术路线网络构建** | TechRouteQuerier + NetworkX构建有向图 | 仅简单拼接实体文本 |
| **RE关系利用** | 利用RE数据构建实体关系网络 | 未使用RE数据 |
| **实验方案8维度** | ExpSchemeRetriever按8维度分类 | 简化分类，缺少完整8维度 |
| **Jc条件补充** | LLM从Content原文补充温度/磁场/角度 | 仅从NER参数字段提取 |
| **Content原文利用** | 构建Jc→Content映射，LLM分析原文 | 未使用Content数据 |
| **Excel上传分析** | `/api/deep-reasoning/upload-excel` API | 无此功能 |
| **LLM分析深度** | 详细8维度对比Prompt | 简单Prompt，缺少深度 |

### 2.2 当前报告内容问题

查看生成的报告 `10.1016_j.physc.2012.10.010_...comprehensive_...md`：

1. **技术路线描述过于简单**: 仅列出材料和工艺名称，缺少关系网络
2. **实验方案维度不完整**: 只有material_fabrication、deposition_techniques、process_parameters，缺少其他5个维度
3. **Jc指标异常**: 出现-1.0 A/cm²等异常值，说明提取逻辑有问题
4. **LLM分析缺乏深度**: Prompt未包含相似论文的详细信息对比要求
5. **分析状态显示失败**: 报告末尾显示"综合分析失败: "（空消息）

---

## 三、改进方案

### 3.1 改进优先级

| 优先级 | 改进项 | 说明 |
|--------|--------|------|
| **P0** | Jc指标提取修复 | 解决-1.0等异常值问题 |
| **P0** | Content原文利用 | Jc条件参数需要从原文补充 |
| **P1** | 技术路线网络构建 | 引入NetworkX构建实体关系图 |
| **P1** | 完整8维度分类 | 补充缺失的5个维度 |
| **P1** | LLM分析Prompt优化 | 添加详细对比分析要求 |
| **P2** | Excel上传分析API | 添加从Excel分析的功能 |

### 3.2 具体改进内容

#### 改进1: Jc指标提取逻辑修复

**问题**: `_extract_jc_conditions()`方法过于简化，未正确处理Jc实体

**改进方案**:
```python
# 参考V2的JcIndexExtractor逻辑
def _extract_jc_conditions_improved(self, entities, pdf_content):
    """
    改进的Jc提取逻辑
    1. 正确识别Transport_Behavior类型的Jc实体
    2. 从value字段解析数值（而非entity_text）
    3. 从parameters字段提取条件参数
    4. 如参数缺失，调用LLM从content原文补充
    """
    jc_indicators = []

    for entity in entities:
        # 检查是否是Jc实体
        if entity.get("type") == "Transport_Behavior":
            symbol = entity.get("symbol", "")
            if symbol in ["Jc", "J_c", "critical current density", "J"]:
                # 从value字段获取数值
                jc_value = entity.get("value")
                if jc_value and jc_value > 0:  # 过滤异常值
                    jc_indicators.append({
                        "jc_value": float(jc_value),
                        "unit": entity.get("unit", "A/cm²"),
                        "parameters": entity.get("parameters", [])
                    })

    # 补充条件参数（调用LLM）
    # ...
```

#### 改进2: Content原文利用

**新增功能**:
```python
async def _supplement_jc_conditions_with_llm(self, jc_indicators, content_text):
    """
    从原文补充Jc条件参数
    参考: V2的JcService._supplement_conditions_with_llm()
    """
    # 检查哪些Jc指标缺少条件参数
    incomplete = [jc for jc in jc_indicators
                  if not jc.get("temperature") or not jc.get("magnetic_field")]

    if incomplete:
        # 批量调用LLM从原文提取条件
        prompt = f"从以下原文中提取Jc测量的温度、磁场、角度条件:\n{content_text}"
        llm_result = await self.llm.chat(prompt, json_mode=True)
        # 更新条件参数
        # ...
```

#### 改进3: 技术路线网络构建

**新增方法**:
```python
def _build_techroute_network(self, entities, relations):
    """
    构建技术路线网络图
    参考: V2的TechRouteQuerier.process_single_ner_re()
    """
    import networkx as nx

    G = nx.DiGraph()

    # 添加实体节点
    for entity in entities:
        G.add_node(entity["id"],
                   type=entity["type"],
                   text=entity.get("symbol"))

    # 添加关系边
    for relation in relations:
        G.add_edge(relation["source_entity"],
                   relation["target_entity"],
                   type=relation["relation_type"])

    # 提取关键路径
    # ...

    return techroute_text, paths
```

#### 改进4: 完整8维度分类

**改进 `_parse_dimensions()`方法**:
```python
def _parse_dimensions_complete(self, entities):
    """
    完整8维度分类
    """
    dimensions = {
        "material_fabrication": [],      # Material_Fabrication
        "deposition_techniques": [],     # Deposition_Techniques
        "process_parameters": [],        # Process_Parameters
        "post_processing": [],           # Post-Processing
        "characterization_techniques": [], # Characterization_Techniques
        "system_constraints": [],        # System_Constraints
        "simulation": [],                # Simulation
        "irradiation": []                # Irradiation
    }

    SUBTYPE_MAPPING = {
        'Material_Fabrication': 'material_fabrication',
        'Deposition_Techniques': 'deposition_techniques',
        'Process_Parameters': 'process_parameters',
        'Post-Processing': 'post_processing',
        'Characterization_Techniques': 'characterization_techniques',
        'System_Constraints': 'system_constraints',
        'Simulation': 'simulation',
        'Irradiation': 'irradiation'
    }

    for entity in entities:
        subtype = entity.get("subtype", "")
        if subtype in SUBTYPE_MAPPING:
            dim_key = SUBTYPE_MAPPING[subtype]
            entity_text = entity.get("symbol", entity.get("value", ""))
            dimensions[dim_key].append(entity_text)

    return dimensions
```

#### 改进5: LLM分析Prompt优化

**改进 `_build_comparison_prompt()`方法**:
```python
def _build_comparison_prompt_improved(self, tech_route, exp_scheme, jc, pdf_content):
    """
    详细LLM对比分析Prompt
    参考: V2的_generate_llm_comparison()
    """
    prompt = """你是超导材料领域的专家，请对以下论文进行详细对比分析。

## 目标论文信息
DOI: {doi}
技术路线：{tech_route_text}
实验方案：{exp_scheme_text}

## 相似论文列表
{similar_papers_detail}

请从以下维度进行深入分析：
1. 技术路线对比：分析目标论文与相似论文在技术路线上的异同点
2. 实验方案对比（8个维度）：
   2.1 材料准备：原材料选择、预处理、合成方法
   2.2 沉积技术：薄膜沉积方法（CVD, PLD, MOD, Sputtering等）
   2.3 工艺参数：温度、时间、气氛、压力等参数设置
   2.4 后处理：热处理、退火、轧制等后处理工艺
   2.5 表征技术：使用的测试和表征方法（XRD, SEM, TEM等）
   2.6 系统约束：设备限制、基底选择、架构设计
   2.7 模拟分析：理论计算和模拟研究
   2.8 辐照处理：粒子辐照、掺杂等特殊处理
3. 关键差异总结
4. 技术趋势分析

请以JSON格式返回分析结果。
"""
```

#### 改进6: 新增Excel上传分析API

**新增API端点**:
```python
@router.post("/from-excel", summary="从Excel执行综合分析")
async def analyze_from_excel(
    file: UploadFile = File(...),
    target_doi: Optional[str] = None,
    top_k: int = 10,
    user = Depends(get_current_user_required)
):
    """
    从上传的Excel文件执行综合分析

    Excel需包含3个sheet: NER, RE, Content
    """
    # 解析Excel
    df_ner = pd.read_excel(file, sheet_name="NER")
    df_re = pd.read_excel(file, sheet_name="RE")
    df_content = pd.read_excel(file, sheet_name="Content")

    # 执行综合分析
    service = get_comprehensive_service()
    result = await service.run_full_analysis_from_excel(
        df_ner=df_ner,
        df_re=df_re,
        df_content=df_content,
        target_doi=target_doi,
        top_k=top_k
    )

    return result
```

---

## 四、实施计划

### Phase 1: 核心功能修复 (P0)

**预计时间**: 1-2天

1. **修复Jc指标提取逻辑**
   - 检查`comprehensive_service.py`的`_extract_jc_conditions()`
   - 修复异常值过滤（-1.0等）
   - 正确从value字段解析数值

2. **添加Content原文利用**
   - 新增`_supplement_jc_conditions_with_llm()`方法
   - 从PDF解析的原文补充Jc条件参数

### Phase 2: 深度分析增强 (P1)

**预计时间**: 2-3天

1. **技术路线网络构建**
   - 引入NetworkX构建实体关系图
   - 利用RE数据构建技术路线

2. **完整8维度分类**
   - 改进`_parse_dimensions()`方法
   - 确保所有8个维度都能提取

3. **LLM分析Prompt优化**
   - 参考V2的详细Prompt结构
   - 添加8维度对比分析要求

### Phase 3: 功能扩展 (P2)

**预计时间**: 1天

1. **Excel上传分析API**
   - 新增`/comprehensive/from-excel`端点
   - 支持上传NER+RE+Content Excel进行分析

---

## 五、验收标准

### 功能验收

1. Jc指标提取正确，无异常值（-1.0等）
2. 报告包含完整的8维度分析
3. LLM分析包含详细的对比内容
4. 技术路线描述包含材料-工艺-参数关系链
5. 支持从Excel上传执行分析

### 报告内容验收

生成的报告应包含：
- 完整的技术路线描述（含关系网络）
- 8维度实验方案分析
- 正确的Jc指标值和排名
- LLM详细对比分析（含8维度对比）
- 技术趋势分析和建议

---

## 六、参考代码文件

### V2核心文件

| 文件路径 | 功能 |
|---------|------|
| `Article_Analysis_System_v2/backend/services/deep_reasoning_service.py` | 综合分析编排服务 |
| `Article_Analysis_System_v2/backend/services/jc_service.py` | Jc指标专项服务 |
| `Article_Analysis_System_v2/deep-reasoning-methods/tech_route/techroute_querier.py` | 技术路线构建 |
| `Article_Analysis_System_v2/deep-reasoning-methods/exp_scheme/exp_scheme_retriever.py` | 实验方案检索 |
| `Article_Analysis_System_v2/deep-reasoning-methods/jc_index/jc_index_extractor.py` | Jc指标提取 |
| `Article_Analysis_System_v2/DEEP_REASONING_ANALYSIS.md` | 深度推理分析文档 |

### V3需修改文件

| 文件路径 | 改进内容 |
|---------|---------|
| `backend/app/services/comprehensive_service.py` | 核心改进 |
| `backend/app/api/v1/comprehensive.py` | 新增Excel上传API |
| `backend/app/services/jc_database_service.py` | Jc检索优化 |

---

**审核状态**: 待审核