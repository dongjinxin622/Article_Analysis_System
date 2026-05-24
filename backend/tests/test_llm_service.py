"""
LLM 服务测试

覆盖：
- parse_json_response 各种输入格式解析
- 空输入、纯 JSON、markdown 代码块包裹、嵌套代码块
"""
import pytest
from backend.app.services.llm_service import LLMService


@pytest.fixture
def llm_svc():
    """创建 LLM 实例（不连接真实 API）"""
    return LLMService(api_key="fake", base_url="http://fake", model="fake")


# ============================================================================
# parse_json_response 测试
# ============================================================================

class TestParseJsonResponse:
    """JSON 响应解析测试"""

    def test_empty_string(self, llm_svc):
        """空字符串返回空列表"""
        assert llm_svc.parse_json_response("") == []
        assert llm_svc.parse_json_response("  ") == []

    def test_none_like_empty(self, llm_svc):
        """仅空白字符视为空"""
        assert llm_svc.parse_json_response("\n\t") == []

    def test_direct_json_object(self, llm_svc):
        """直接 JSON 对象"""
        text = '{"name": "YBCO", "type": "Material"}'
        result = llm_svc.parse_json_response(text)
        assert result["name"] == "YBCO"
        assert result["type"] == "Material"

    def test_direct_json_array(self, llm_svc):
        """直接 JSON 数组"""
        text = '[{"id": 1}, {"id": 2}]'
        result = llm_svc.parse_json_response(text)
        assert len(result) == 2
        assert result[0]["id"] == 1

    def test_json_in_markdown_code_block(self, llm_svc):
        """```json 代码块中的 JSON"""
        text = '分析结果如下：\n```json\n{"entities": ["A", "B"]}\n```'
        result = llm_svc.parse_json_response(text)
        assert result["entities"] == ["A", "B"]

    def test_json_in_bare_code_block(self, llm_svc):
        """``` 代码块中的 JSON（无 json 标记）"""
        text = '结果:\n```\n{"score": 0.95}\n```'
        result = llm_svc.parse_json_response(text)
        assert result["score"] == 0.95

    def test_json_with_surrounding_text_returns_none(self, llm_svc):
        """前后有非 JSON 文本且无代码块包裹时无法提取"""
        text = '以下是提取的实体:\n{"count": 3}\n以上为结果'
        result = llm_svc.parse_json_response(text)
        # 没有代码块包裹时，json5 无法从混合文本中提取
        assert result is None

    def test_json_code_block_preferred_over_bare(self, llm_svc):
        """```json 优先于 ``` 提取"""
        text = '```json\n{"priority": "high"}\n```\n```\n{"priority": "low"}\n```'
        result = llm_svc.parse_json_response(text)
        assert result["priority"] == "high"

    def test_invalid_json_returns_none(self, llm_svc):
        """完全无效的 JSON 返回 None"""
        text = "这是一段非 JSON 文本，没有任何可解析的内容"
        result = llm_svc.parse_json_response(text)
        assert result is None

    def test_json5_features(self, llm_svc):
        """json5 特性：尾逗号、单引号"""
        text = "{name: 'YBCO', count: 5,}"
        result = llm_svc.parse_json_response(text)
        assert result["name"] == "YBCO"
        assert result["count"] == 5

    def test_nested_json(self, llm_svc):
        """嵌套 JSON 结构"""
        text = '{"outer": {"inner": [{"val": 1}]}}'
        result = llm_svc.parse_json_response(text)
        assert result["outer"]["inner"][0]["val"] == 1

    def test_multiline_json_in_code_block(self, llm_svc):
        """多行 JSON 在代码块中"""
        text = '```json\n{\n  "type": "superconductor",\n  "jc": 1.5e6\n}\n```'
        result = llm_svc.parse_json_response(text)
        assert result["type"] == "superconductor"
        assert result["jc"] == 1.5e6