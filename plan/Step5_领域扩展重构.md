# Step5: 领域扩展重构 - 详细计划

> 预计周期: 2 周 | 状态: 待开始 | 前置依赖: Step4

---

## 一、任务清单

### 5.1 领域分析器基类设计

**目标**：设计可扩展的领域分析器基类

**文件**：`backend/app/domain/base.py`

**参考来源**：架构设计文档领域分析器设计

**基类设计**：
```python
from abc import ABC, abstractmethod

class DomainAnalyzerBase(ABC):
    """领域分析器基类"""

    def __init__(self, embedding_service, vector_service):
        self.embedding_service = embedding_service
        self.vector_service = vector_service

    @abstractmethod
    def get_entity_types(self) -> Dict[str, str]:
        """返回领域实体类型定义"""
        pass

    @abstractmethod
    def get_relation_types(self) -> Dict[str, str]:
        """返回领域关系类型定义"""
        pass

    @abstractmethod
    def get_prompt_template(self) -> str:
        """返回 NER Prompt 模板"""
        pass

    @abstractmethod
    async def build_profile(self, ner_result) -> str:
        """构建领域特征描述"""
        pass

    @abstractmethod
    async def analyze(self, input_data) -> Dict:
        """执行领域特定分析"""
        pass

    async def retrieve_similar(self, profile, domain, top_k=10):
        """从 Milvus 检索相似论文"""
        vector = await self.embedding_service.embed_text(profile)
        results = await self.vector_service.search_similar_tech_routes(
            query_vector=vector,
            domain=domain,
            top_k=top_k
        )
        return results

    async def store_profile_vector(self, paper_id, profile, domain):
        """将技术路线向量存储到 Milvus"""
        vector = await self.embedding_service.embed_text(profile)
        await self.vector_service.insert_tech_route_vector(
            paper_id=paper_id,
            profile_text=profile,
            embedding=vector,
            domain=domain
        )
```

---

### 5.2 领域注册中心实现

**目标**：实现领域分析器注册机制

**文件**：`backend/app/domain/registry.py`

**参考来源**：架构设计文档领域注册中心

**功能设计**：
```python
class DomainRegistry:
    """领域分析器注册中心"""

    _analyzers: Dict[str, DomainAnalyzerBase] = {}

    @classmethod
    def register(cls, domain: str, analyzer: DomainAnalyzerBase):
        """注册领域分析器"""
        cls._analyzers[domain] = analyzer

    @classmethod
    def get(cls, domain: str) -> DomainAnalyzerBase:
        """获取领域分析器"""
        return cls._analyzers.get(domain)

    @classmethod
    def list_domains(cls) -> List[str]:
        """列出所有已注册领域"""
        return list(cls._analyzers.keys())

    @classmethod
    def get_config(cls, domain: str) -> Dict:
        """获取领域配置"""
        analyzer = cls.get(domain)
        if analyzer:
            return {
                'entity_types': analyzer.get_entity_types(),
                'relation_types': analyzer.get_relation_types(),
                'prompt_template': analyzer.get_prompt_template()
            }
        return None
```

---

### 5.3 REBCO 领域分析器迁移

**目标**：迁移 REBCO 超导材料领域分析器

**文件**：`backend/app/domain/material/analyzer.py`

**参考来源**：
- v2 `deep-reasoning-methods/tech_route/techroute_builder.py`
- v2 `deep-reasoning-methods/exp_scheme/exp_scheme_builder.py`
- v2 `deep-reasoning-methods/jc_index/jc_index_extractor.py`

**分析器结构**：
```python
class REBCOAnalyzer(DomainAnalyzerBase):
    """REBCO 超导材料领域分析器"""

    def get_entity_types(self) -> Dict[str, str]:
        return {
            "工艺参数": "制备工艺相关参数",
            "微结构特征": "材料微观结构特征",
            "性能指标": "材料性能参数",
            "Transport_Behavior": "传输行为"
        }

    def get_relation_types(self) -> Dict[str, str]:
        return {
            "因果关系": "工艺参数对性能的影响",
            "相关关系": "实体间的关联",
            "组成关系": "整体与部分关系"
        }

    async def analyze(self, input_data) -> Dict:
        analysis_type = input_data.get("analysis_type")
        if analysis_type == "tech_route":
            return await self._analyze_tech_route(input_data)
        elif analysis_type == "exp_scheme":
            return await self._analyze_exp_scheme(input_data)
        elif analysis_type == "jc_comparison":
            return await self._analyze_jc(input_data)
```

---

### 5.4 技术路线分析迁移

**目标**：迁移技术路线分析功能

**文件**：`backend/app/domain/material/tech_route.py`

**参考来源**：v2 `deep-reasoning-methods/tech_route/`

**核心功能**：
- 从 NER+RE 构建实体网络
- 提取从工艺参数到 Jc 的关键路径
- 生成技术路线文本描述
- 向量化并存储到 Milvus
- 检索相似技术路线论文

---

### 5.5 实验方案分析迁移

**目标**：迁移实验方案分析功能

**文件**：`backend/app/domain/material/exp_scheme.py`

**参考来源**：v2 `deep-reasoning-methods/exp_scheme/`

**核心功能**：
- 从 NER 提取实验方案类别（8维度）
- 生成实验方案文本描述
- 向量化并存储到 Milvus
- 检索相似实验方案论文

**8维度分析**：
1. 材料准备
2. 沉积技术
3. 工艺参数
4. 后处理
5. 表征技术
6. 系统约束
7. 模拟分析
8. 辐照处理

---

### 5.6 Jc 指标分析迁移

**目标**：迁移 Jc 指标提取和分析功能

**文件**：`backend/app/domain/material/jc_index.py`

**参考来源**：v2 `deep-reasoning-methods/jc_index/jc_index_extractor.py`

**核心功能**：
- 从 NER 定位 Jc 相关实体
- 从 Content 定位原文段落
- LLM 提取 Jc 指标（值、温度、磁场、角度）
- 按条件检索相似 Jc 数据
- Jc 对比分析报告

---

### 5.7 领域配置管理 API

**目标**：创建领域配置管理 API

**文件**：`backend/app/api/v1/domain.py`

**参考来源**：架构设计文档 Domain API

**API 接口**：

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/domains` | GET | 获取领域列表 |
| `/api/v1/domains/{name}/config` | GET | 获取领域配置 |
| `/api/v1/domains/{name}/analyze` | POST | 执行领域分析 |
| `/api/v1/domains/{name}/techroute` | POST | 技术路线分析 |
| `/api/v1/domains/{name}/expscheme` | POST | 实验方案分析 |
| `/api/v1/domains/{name}/jc/search` | POST | Jc 条件搜索 |
| `/api/v1/domains/{name}/jc/compare` | POST | Jc 对比分析 |

---

### 5.8 领域配置数据库模型

**目标**：创建领域配置数据库表

**文件**：`backend/app/models/domain.py`

**模型设计**：
```python
class DomainConfig(Base):
    __tablename__ = "domain_configs"

    id = Column(Integer, primary_key=True)
    domain_name = Column(String(100), unique=True)
    entity_types = Column(JSON)
    relation_types = Column(JSON)
    prompt_templates = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime)
```

---

## 二、执行顺序

1. 创建 `backend/app/domain/base.py`
2. 创建 `backend/app/domain/registry.py`
3. 创建 `backend/app/domain/material/__init__.py`
4. 创建 `backend/app/domain/material/tech_route.py`
5. 创建 `backend/app/domain/material/exp_scheme.py`
6. 创建 `backend/app/domain/material/jc_index.py`
7. 创建 `backend/app/domain/material/analyzer.py`
8. 注册 REBCO 分析器
9. 创建 `backend/app/models/domain.py`
10. 创建 `backend/app/api/v1/domain.py`
11. 测试领域分析功能

---

## 三、检查标准

| 检查项 | 标准 |
|--------|------|
| 领域列表 | API 返回已注册领域列表 |
| 领域配置 | 返回正确的实体类型和关系类型 |
| 技术路线分析 | 返回技术路线文本和相似论文 |
| 实验方案分析 | 返回实验方案文本和相似论文 |
| Jc 指标提取 | 提取正确的 Jc 值和条件参数 |
| 向量存储 | 技术路线/实验方案向量存储成功 |
| Milvus 检索 | 相似论文检索返回正确结果 |

---

## 四、参考文件列表

| v2 文件 | v3 目标位置 |
|---------|------------|
| `deep-reasoning-methods/base_methods.py` | 参考基类设计思路 |
| `deep-reasoning-methods/tech_route/techroute_builder.py` | `backend/app/domain/material/tech_route.py` |
| `deep-reasoning-methods/tech_route/techroute_common.py` | 参考网络构建工具 |
| `deep-reasoning-methods/exp_scheme/exp_scheme_builder.py` | `backend/app/domain/material/exp_scheme.py` |
| `deep-reasoning-methods/jc_index/jc_index_extractor.py` | `backend/app/domain/material/jc_index.py` |
| `backend/services/deep_reasoning_service.py` | 参考服务层逻辑 |
| `backend/api/deep_reasoning.py` | `backend/app/api/v1/domain.py` |

---

*Step5 完成后进入 Step6: 异步任务系统*