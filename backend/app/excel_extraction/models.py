"""
动态 Pydantic 模型生成
根据策略文档动态生成评估输出模型
"""
from typing import Type, Optional, List, Dict
from pydantic import BaseModel, Field, create_model


def create_evaluation_model(
    domain_fields: Dict[str, str] = None,
    key_indicators: Dict[str, str] = None,
    extract_fields: List[str] = None
) -> Type[BaseModel]:
    """
    根据配置动态生成评估输出模型

    Args:
        domain_fields: 领域特定字段 {"laser_type": "激光类型描述"}
        key_indicators: 关键指标字段 {"pulse_width": "脉冲宽度描述"}
        extract_fields: 要提取的基础字段列表

    Returns:
        动态生成的 Pydantic 模型类
    """
    domain_fields = domain_fields or {}
    key_indicators = key_indicators or {}
    extract_fields = extract_fields or ["related", "institution", "summary", "key_technologies", "application_areas"]

    # 基础字段定义
    base_fields = {
        "related": (bool, Field(description="是否与目标研究领域相关")),
        "institution": (Optional[str], Field(default="N/A", description="通讯作者所属机构")),
        "summary": (Optional[str], Field(default="N/A", description="论文核心贡献摘要（200字以内）")),
    }

    # 列表类型字段
    list_fields = {
        "key_technologies": (List[str], Field(default_factory=list, description="使用的关键技术列表")),
        "application_areas": (List[str], Field(default_factory=list, description="应用领域列表")),
    }

    # 根据 extract_fields 选择要包含的字段
    fields = {}
    for field_name in extract_fields:
        if field_name in base_fields:
            fields[field_name] = base_fields[field_name]
        elif field_name in list_fields:
            fields[field_name] = list_fields[field_name]

    # 动态添加领域特定字段（字符串类型）
    for field_name, description in domain_fields.items():
        fields[field_name] = (Optional[str], Field(default="N/A", description=description))

    # 动态添加关键指标字段（字符串类型）
    for field_name, description in key_indicators.items():
        fields[field_name] = (Optional[str], Field(default="N/A", description=description))

    # 创建动态模型
    model = create_model("ArticleEvaluation", **fields)

    return model


def model_to_dict(model_class: Type[BaseModel]) -> Dict:
    """
    将 Pydantic 模型转换为可序列化的字典（用于存储到数据库）

    Args:
        model_class: Pydantic 模型类

    Returns:
        模型字段定义字典
    """
    schema = model_class.model_json_schema()
    return {
        "name": schema.get("title", "ArticleEvaluation"),
        "fields": schema.get("properties", {}),
        "required": schema.get("required", []),
    }


def dict_to_field_definitions(model_dict: Dict) -> Dict[str, str]:
    """
    从模型字典提取字段描述（用于生成 Prompt）

    Args:
        model_dict: 模型字典

    Returns:
        字段描述字典 {field_name: description}
    """
    fields = model_dict.get("fields", {})
    descriptions = {}
    for field_name, field_info in fields.items():
        description = field_info.get("description", field_name)
        descriptions[field_name] = description
    return descriptions


# 预定义的默认模型（无领域特定字段）
def get_default_evaluation_model() -> Type[BaseModel]:
    """获取默认评估模型"""
    return create_evaluation_model()


# 示例：材料科学领域模型
def get_material_science_model() -> Type[BaseModel]:
    """获取材料科学领域评估模型"""
    domain_fields = {
        "material_system": "材料体系（如 REBCO 超导材料）",
        "synthesis_method": "合成/制备方法",
        "characterization_technique": "表征技术",
    }
    key_indicators = {
        "critical_temperature": "临界温度（超导材料）",
        "critical_current": "临界电流密度",
    }
    return create_evaluation_model(domain_fields, key_indicators)