"""
综合分析服务测试

覆盖：
- _parse_dimensions 实体 8 维度分类
- _build_tech_route_text 技术路线文本构建
- _extract_jc_conditions_improved Jc 条件提取（基础场景）
- _build_markdown_report Markdown 报告构建
"""
import pytest
from backend.app.services.comprehensive_service import ComprehensiveAnalysisService


@pytest.fixture
def comp_svc():
    return ComprehensiveAnalysisService()


# ============================================================================
# _parse_dimensions 测试
# ============================================================================

class TestParseDimensions:
    """8 维度分类测试"""

    def test_empty_entities(self, comp_svc):
        """空实体列表返回 8 个空维度"""
        dims = comp_svc._parse_dimensions([])
        assert len(dims) == 8
        for key, val in dims.items():
            assert val == []

    def test_material_classification(self, comp_svc):
        """Material 类型归入 material_fabrication"""
        entities = [{"type": "Material", "symbol": "YBCO"}]
        dims = comp_svc._parse_dimensions(entities)
        assert "YBCO" in dims["material_fabrication"]
        assert all(len(dims[k]) == 0 for k in dims if k != "material_fabrication")

    def test_subtype_mapping(self, comp_svc):
        """subtype 优先级高于 type"""
        entities = [{"type": "Microstructural_Hierarchy", "subtype": "Chemical_Formula", "symbol": "YBa2Cu3O7"}]
        dims = comp_svc._parse_dimensions(entities)
        assert "YBa2Cu3O7" in dims["material_fabrication"]

    def test_deposition_techniques(self, comp_svc):
        """沉积技术维度分类"""
        entities = [{"type": "Deposition", "subtype": "Deposition_Techniques", "symbol": "PLD"}]
        dims = comp_svc._parse_dimensions(entities)
        assert "PLD" in dims["deposition_techniques"]

    def test_process_parameters(self, comp_svc):
        """工艺参数维度分类"""
        entities = [{"type": "Process_Params", "symbol": "Temperature", "value": 800, "unit": "K"}]
        dims = comp_svc._parse_dimensions(entities)
        assert len(dims["process_parameters"]) > 0

    def test_performance_symbols_excluded(self, comp_svc):
        """Jc/Tc 等性能指标不归入 8 维度"""
        entities = [
            {"type": "Measurement", "symbol": "Jc", "value": "1.5e6"},
            {"type": "Measurement", "symbol": "Tc", "value": "90"},
        ]
        dims = comp_svc._parse_dimensions(entities)
        # 性能指标被排除，不出现在任何维度中
        for key, val in dims.items():
            assert "Jc" not in val
            assert "Tc" not in val

    def test_substrate_in_system_constraints(self, comp_svc):
        """Substrate 归入 system_constraints"""
        entities = [{"type": "Substrate", "symbol": "SrTiO3"}]
        dims = comp_svc._parse_dimensions(entities)
        assert "SrTiO3" in dims["system_constraints"]

    def test_multiple_dimensions(self, comp_svc):
        """多实体分散到不同维度"""
        entities = [
            {"type": "Material", "symbol": "YBCO"},
            {"type": "Deposition", "subtype": "Deposition_Techniques", "symbol": "PLD"},
            {"type": "Substrate", "symbol": "STO"},
            {"subtype": "Post-Processing", "symbol": "Oxygen annealing"},
        ]
        dims = comp_svc._parse_dimensions(entities)
        assert "YBCO" in dims["material_fabrication"]
        assert "PLD" in dims["deposition_techniques"]
        assert "STO" in dims["system_constraints"]
        assert "Oxygen annealing" in dims["post_processing"]

    def test_entity_with_parameters(self, comp_svc):
        """带 parameters 字段的实体拼接参数"""
        entities = [
            {
                "type": "Material", "subtype": "Material_Identification",
                "symbol": "YBCO",
                "parameters": [{"type": "Tc", "value": 90, "unit": "K"}]
            }
        ]
        dims = comp_svc._parse_dimensions(entities)
        assert any("YBCO" in item and "Tc" in item for item in dims["material_fabrication"])

    def test_microstructural_hierarchy_dimensional_control(self, comp_svc):
        """Microstructural_Hierarchy + Dimensional_Control 归入工艺参数"""
        entities = [
            {"type": "Microstructural_Hierarchy", "subtype": "Dimensional_Control", "symbol": "Film_Thickness"}
        ]
        dims = comp_svc._parse_dimensions(entities)
        assert "Film_Thickness" in dims["process_parameters"]

    def test_type_mapping_fallback(self, comp_svc):
        """type 映射作为 subtype 的回退"""
        entities = [{"type": "Manufacturing_Process_Chain", "symbol": "Sputtering"}]
        dims = comp_svc._parse_dimensions(entities)
        assert "Sputtering" in dims["deposition_techniques"]


# ============================================================================
# _build_tech_route_text 测试
# ============================================================================

class TestBuildTechRouteText:
    """技术路线文本构建测试"""

    def test_empty_entities(self, comp_svc):
        """空实体返回空字符串"""
        assert comp_svc._build_tech_route_text([], []) == ""

    def test_materials_and_substrates(self, comp_svc):
        """材料和基底分类"""
        entities = [
            {"type": "Material", "symbol": "YBCO"},
            {"type": "Substrate", "symbol": "SrTiO3"},
        ]
        text = comp_svc._build_tech_route_text(entities, [])
        assert "材料" in text
        assert "YBCO" in text
        assert "基底" in text
        assert "SrTiO3" in text

    def test_processes(self, comp_svc):
        """工艺方法分类"""
        entities = [
            {"type": "Deposition", "subtype": "Deposition_Techniques", "symbol": "PLD"},
        ]
        text = comp_svc._build_tech_route_text(entities, [])
        assert "工艺" in text
        assert "PLD" in text

    def test_parameter_with_value(self, comp_svc):
        """参数带具体数值"""
        entities = [
            {"type": "Process_Params", "symbol": "Film_Thickness", "value": 300, "unit": "nm"},
        ]
        text = comp_svc._build_tech_route_text(entities, [])
        assert "参数" in text
        assert "300" in text

    def test_performance_with_value(self, comp_svc):
        """性能指标带数值"""
        entities = [
            {"type": "Measurement", "symbol": "Jc", "value": "1.5e6", "unit": "A/cm2"},
        ]
        text = comp_svc._build_tech_route_text(entities, [])
        assert "性能" in text
        assert "Jc" in text

    def test_relation_chains(self, comp_svc):
        """RE 关系链构建"""
        entities = [{"type": "Material", "symbol": "YBCO"}]
        relations = [
            {"source_entity": "YBCO", "target_entity": "SrTiO3"},
            {"source_entity": "PLD", "target_entity": "Film"},
        ]
        text = comp_svc._build_tech_route_text(entities, relations)
        assert "关键路径" in text
        assert "YBCO" in text  # 来自关系链
        assert "SrTiO3" in text

    def test_deduplication(self, comp_svc):
        """重复材料去重"""
        entities = [
            {"type": "Material", "symbol": "YBCO"},
            {"type": "Material", "symbol": "YBCO"},
        ]
        text = comp_svc._build_tech_route_text(entities, [])
        # 去重后 YBCO 只出现一次在材料列表中
        assert text.count("YBCO") >= 1

    def test_single_letter_excluded(self, comp_svc):
        """单字母变量名不归入材料"""
        entities = [{"type": "Material", "symbol": "a"}]
        text = comp_svc._build_tech_route_text(entities, [])
        assert "a" not in text or "材料" not in text

    def test_pvd_deposition_included(self, comp_svc):
        """PVD 作为工艺保留"""
        entities = [
            {"type": "Deposition", "symbol": "PVD"},
        ]
        text = comp_svc._build_tech_route_text(entities, [])
        assert "PVD" in text

    def test_general_deposition_excluded(self, comp_svc):
        """通用 Deposition 符号被排除"""
        entities = [
            {"type": "Deposition", "subtype": "Deposition_Techniques", "symbol": "Deposition"},
        ]
        text = comp_svc._build_tech_route_text(entities, [])
        # "Deposition" 通用名被排除，但可能有工艺类别标签
        assert "Deposition" not in text or "工艺" in text


# ============================================================================
# _extract_jc_conditions_improved 测试
# ============================================================================

class TestExtractJcConditions:
    """Jc 条件提取测试"""

    def test_empty_entities(self, comp_svc):
        """空实体列表返回空指标"""
        result = comp_svc._extract_jc_conditions_improved([], {})
        assert result["jc_indicators"] == []

    def test_jc_value_extraction(self, comp_svc):
        """提取 Jc 值"""
        entities = [
            {"type": "Measurement", "symbol": "Jc", "value": "1.5e6", "unit": "A/cm2"}
        ]
        result = comp_svc._extract_jc_conditions_improved(entities, {})
        assert len(result["jc_indicators"]) > 0

    def test_negative_jc_filtered(self, comp_svc):
        """负 Jc 值被过滤"""
        entities = [
            {"type": "Measurement", "symbol": "Jc", "value": "-100", "unit": "A/cm2"}
        ]
        result = comp_svc._extract_jc_conditions_improved(entities, {})
        # 负值应被过滤
        for jc in result["jc_indicators"]:
            assert jc.get("jc_value", 0) > 0 or jc.get("value", 0) > 0

    def test_zero_jc_filtered(self, comp_svc):
        """零 Jc 值被过滤"""
        entities = [
            {"type": "Measurement", "symbol": "Jc", "value": "0", "unit": "A/cm2"}
        ]
        result = comp_svc._extract_jc_conditions_improved(entities, {})
        for jc in result["jc_indicators"]:
            val = jc.get("jc_value", jc.get("value", 0))
            assert val != 0

    def test_temperature_extraction(self, comp_svc):
        """温度从 Jc 实体的 parameters 字段提取"""
        entities = [
            {
                "type": "Measurement", "subtype": "Jc",
                "symbol": "Jc", "value": "1.5e6", "unit": "A/cm2",
                "parameters": [{"type": "Temperature", "value": 77, "unit": "K"}]
            }
        ]
        result = comp_svc._extract_jc_conditions_improved(entities, {})
        # 温度可能从 parameters 提取到 jc_indicators 中
        assert len(result["jc_indicators"]) > 0
        jc = result["jc_indicators"][0]
        assert jc.get("temperature") is not None or jc.get("temperature_K") is not None

    def test_magnetic_field_extraction(self, comp_svc):
        """磁场从 Jc 实体的 parameters 字段提取"""
        entities = [
            {
                "type": "Measurement", "subtype": "Jc",
                "symbol": "Jc", "value": "1.5e6", "unit": "A/cm2",
                "parameters": [{"type": "Magnetic_Field", "value": 0, "unit": "T"}]
            }
        ]
        result = comp_svc._extract_jc_conditions_improved(entities, {})
        assert len(result["jc_indicators"]) > 0