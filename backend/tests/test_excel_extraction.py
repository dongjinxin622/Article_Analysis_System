"""
Excel 批量题录提取功能测试

测试数据使用 excel_section_test_sample 目录中的文件
覆盖：上传/预览、任务 CRUD、数据节点处理
"""
import pytest
import sys
import os
import json
import tempfile
import asyncio
import pandas as pd
from pathlib import Path

# 项目根目录（backend/tests/ -> backend/ -> 项目根）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================================
# 测试配置
# ============================================================================

SAMPLE_DIR = PROJECT_ROOT / "excel_section_test_sample"


def pytest_configure(config):
    config.addinivalue_line("asyncio_default_fixture_loop_scope", "function")


def get_sample_excel_path() -> str:
    """获取测试用 Excel 文件路径"""
    for f in SAMPLE_DIR.glob("*.xls*"):
        return str(f)
    raise FileNotFoundError(f"未在 {SAMPLE_DIR} 中找到 .xls/.xlsx 文件")


def get_sample_docx_path() -> str:
    """获取测试用策略文档路径"""
    for f in SAMPLE_DIR.glob("*.docx"):
        return str(f)
    return None


# ============================================================================
# 文件上传与数据预览测试
# ============================================================================

class TestExcelUpload:
    """Excel 文件上传与数据预览测试"""

    def test_sample_files_exist(self):
        """验证测试样本文件存在"""
        excel_path = get_sample_excel_path()
        assert os.path.exists(excel_path), f"Excel 文件不存在: {excel_path}"
        print(f"[OK] Excel 文件: {excel_path} ({os.path.getsize(excel_path)} bytes)")

    def test_read_excel(self):
        """验证能正确读取 Excel 文件"""
        excel_path = get_sample_excel_path()
        df = pd.read_excel(excel_path)
        assert len(df) > 0, "DataFrame 为空"
        assert len(df.columns) > 0, "列数为 0"
        print(f"[OK] 读取成功: {len(df)} 行, {len(df.columns)} 列")
        print(f"     列名: {list(df.columns)}")

    def test_column_normalization(self):
        """验证列名标准化"""
        excel_path = get_sample_excel_path()
        df = pd.read_excel(excel_path)

        column_mapping = {
            "DOI": "doi", "doi": "doi",
            "Title": "title", "title": "title", "Article Title": "title",
            "Abstract": "abstract", "abstract": "abstract",
            "Authors": "authors", "authors": "authors",
            "Year": "year", "year": "year",
            "Journal": "journal", "journal": "journal",
        }
        df.columns = [column_mapping.get(c, c.lower()) for c in df.columns]

        # 检查必要字段
        for field in ["doi", "title", "abstract"]:
            assert field in df.columns, f"缺失必要字段: {field}"

        missing_doi = df["doi"].isna().sum() + (df["doi"] == "").sum()
        print(f"[OK] 列名标准化完成，DOI 缺失: {missing_doi}/{len(df)}")

    def test_quality_stats(self):
        """验证数据质量统计"""
        excel_path = get_sample_excel_path()
        df = pd.read_excel(excel_path)

        column_mapping = {
            "DOI": "doi", "doi": "doi",
            "Title": "title", "title": "title", "Article Title": "title",
            "Abstract": "abstract", "abstract": "abstract",
        }
        df.columns = [column_mapping.get(c, c.lower()) for c in df.columns]

        required_fields = ["doi", "title", "abstract"]
        quality = {}
        for field in required_fields:
            if field in df.columns:
                missing = int(df[field].isna().sum() + (df[field] == "").sum())
                quality[f"missing_{field}"] = missing
            else:
                quality[f"missing_{field}"] = len(df)

        for key, val in quality.items():
            rate = val / len(df) * 100
            print(f"     {key}: {val} ({rate:.1f}%)")

        # 至少有一条 DOI 不缺失的记录可用于测试
        assert quality.get("missing_doi", len(df)) < len(df), "所有记录的 DOI 都缺失"
        print(f"[OK] 质量统计完成")


class TestMultiFileMerge:
    """多文件合并测试"""

    def test_merge_xls_files(self):
        """验证多个 Excel 文件合并"""
        dfs = []
        for f in SAMPLE_DIR.glob("*.xls*"):
            df = pd.read_excel(str(f))
            dfs.append(df)
            print(f"     文件: {f.name} -> {len(df)} 行")

        assert len(dfs) > 0, "未找到任何 Excel 文件"
        merged = pd.concat(dfs, ignore_index=True)
        assert len(merged) >= len(dfs[0]), "合并后行数异常"
        print(f"[OK] 合并完成: {len(dfs)} 个文件 -> {len(merged)} 行")


# ============================================================================
# 数据节点处理测试
# ============================================================================

class TestDataNodes:
    """数据处理节点单元测试（不依赖 WebSocket）"""

    def test_load_data_with_sample(self):
        """加载样本数据并验证结构"""
        excel_path = get_sample_excel_path()
        df = pd.read_excel(excel_path)

        input_dict = {}
        for idx, row in df.iterrows():
            doi = str(row.get("DOI", row.get("doi", f"unknown_{idx}")))
            row_dict = row.to_dict()
            # 标准化键名为小写
            row_dict = {str(k).lower(): v for k, v in row_dict.items()}
            input_dict[doi] = row_dict

        assert len(input_dict) > 0, "input_dict 为空"
        # 验证每条记录包含必要字段
        first_key = list(input_dict.keys())[0]
        first_record = input_dict[first_key]
        assert "doi" in first_record or "DOI" not in str(first_record), \
            f"记录中无 doi 字段: {list(first_record.keys())[:5]}"
        print(f"[OK] input_dict 构建成功: {len(input_dict)} 条记录")

    def test_field_check_simulation(self):
        """模拟字段检查节点逻辑"""
        excel_path = get_sample_excel_path()
        df = pd.read_excel(excel_path)

        required_fields = ["doi", "title", "abstract"]
        missing_stats = {}
        for field in required_fields:
            col = None
            for c in df.columns:
                if c.lower() == field.lower():
                    col = c
                    break
            if col:
                count = int(df[col].isna().sum() + (df[col].astype(str).str.strip() == "").sum())
                missing_stats[field] = count
            else:
                missing_stats[field] = len(df)

        failed = sum(1 for v in missing_stats.values() if v > 0)
        print(f"     缺失统计: {missing_stats}")
        print(f"     问题字段数: {failed}")

        # 验证结果结构
        assert isinstance(missing_stats, dict)
        for field in required_fields:
            assert field in missing_stats

    def test_deduplication(self):
        """验证 DOI 去重逻辑"""
        excel_path = get_sample_excel_path()
        df = pd.read_excel(excel_path)

        # 构建 input_dict 并检查重复
        dois = []
        for idx, row in df.iterrows():
            doi = str(row.get("DOI", row.get("doi", "")))
            if doi and doi != "nan":
                dois.append(doi)

        unique_dois = set(dois)
        dup_count = len(dois) - len(unique_dois)
        print(f"     总 DOI 数: {len(dois)}, 唯一: {len(unique_dois)}, 重复: {dup_count}")

        assert len(unique_dois) > 0, "无有效 DOI"
        print(f"[OK] 去重完成，重复率: {dup_count/len(dois)*100:.1f}%" if dois else "[OK] 无 DOI 数据")


# ============================================================================
# 任务 CRUD 与状态机测试
# ============================================================================

class TestTaskWorkflow:
    """任务工作流状态机测试"""

    def test_task_status_transitions(self):
        """验证任务状态转换逻辑"""
        from backend.app.schemas.excel_extraction import ExcelExtractionTaskStatus

        # 允许的状态转换
        valid_transitions = {
            "pending": ["validating", "processing", "failed", "cancelled"],
            "validating": ["processing", "failed", "cancelled"],
            "processing": ["hitl_waiting", "exporting", "completed", "failed", "cancelled"],
            "hitl_waiting": ["processing", "validating", "failed", "cancelled"],
            "exporting": ["completed", "failed"],
            "completed": [],  # 终态
            "failed": [],
            "cancelled": [],
        }

        for status, allowed in valid_transitions.items():
            status_enum = ExcelExtractionTaskStatus(status)
            assert status_enum.value == status
            print(f"     {status} -> {allowed}")

    def test_config_validation(self):
        """验证任务配置 Schema"""
        from backend.app.schemas.excel_extraction import TaskConfig

        config = TaskConfig(
            domain_fields=[],
            extract_fields=["related", "institution", "summary"],
            max_concurrent=5,
            quality_threshold=0.6,
            enable_smart_hitl=True,
        )

        assert config.max_concurrent == 5
        assert config.quality_threshold == 0.6
        assert config.enable_smart_hitl is True
        print(f"[OK] 配置验证通过: max_concurrent={config.max_concurrent}, "
              f"extract_fields={config.extract_fields}")


# ============================================================================
# HITL 上下文测试
# ============================================================================

class TestHITLContext:
    """WebHITLContext 上下文管理测试"""

    @pytest.mark.asyncio
    async def test_context_lifecycle(self):
        """验证 HITL 上下文创建/获取/移除/中断生命周期"""
        from backend.app.excel_extraction.llm_hitl_nodes import WebHITLContext

        sid = "test_context_lifecycle"

        ctx = await WebHITLContext.get(sid)
        assert ctx.session_id == sid
        assert ctx._aborted is False
        print(f"[OK] 上下文创建: {sid}")

        # 验证同步获取
        ctx_sync = WebHITLContext.get_sync(sid)
        assert ctx_sync is ctx
        print(f"[OK] get_sync 返回同一实例")

        # 验证 abort
        ctx.abort("测试中断")
        assert ctx._aborted is True
        assert ctx._pending_action == "continue"
        print(f"[OK] abort 完成，pending_action={ctx._pending_action}")

        # 验证 remove 会先 abort
        sid2 = "test_context_remove"
        ctx2 = await WebHITLContext.get(sid2)
        await WebHITLContext.remove(sid2)
        assert ctx2._aborted is True
        # 从 _instances 中移除
        assert WebHITLContext.get_sync(sid2) is None
        print(f"[OK] remove 触发了 abort 并清理了实例")

    @pytest.mark.asyncio
    async def test_wait_timeout(self):
        """验证 HITL 等待超时机制"""
        from backend.app.excel_extraction.llm_hitl_nodes import WebHITLContext

        sid = "test_wait_timeout"
        # 缩短超时以便测试
        original_timeout = WebHITLContext.HITL_TIMEOUT
        WebHITLContext.HITL_TIMEOUT = 1  # 1 秒超时

        try:
            ctx = await WebHITLContext.get(sid)
            await ctx._wait_for_action()
            # 超时后应自动设置 continue
            assert ctx._pending_action == "continue"
            print(f"[OK] 超时后自动设置为 continue")
        finally:
            WebHITLContext.HITL_TIMEOUT = original_timeout
            await WebHITLContext.remove(sid)

    @pytest.mark.asyncio
    async def test_abort_wakes_wait(self):
        """验证 abort 能唤醒正在等待的 _wait_for_action"""
        from backend.app.excel_extraction.llm_hitl_nodes import WebHITLContext

        sid = "test_abort_wakes"
        ctx = await WebHITLContext.get(sid)

        # 启动一个异步任务来 abort
        async def delayed_abort():
            await asyncio.sleep(0.1)
            ctx.abort("外部中断")

        abort_task = asyncio.create_task(delayed_abort())

        # 此调用应被 abort 唤醒
        await ctx._wait_for_action()
        await abort_task  # 确保任务完成

        assert ctx._aborted is True
        assert ctx._pending_action == "continue"
        print(f"[OK] abort 成功唤醒等待")

        await WebHITLContext.remove(sid)

    @pytest.mark.asyncio
    async def test_concurrent_get(self):
        """验证并发获取同一上下文"""
        from backend.app.excel_extraction.llm_hitl_nodes import WebHITLContext

        sid = "test_concurrent"
        ctx1, ctx2 = await asyncio.gather(
            WebHITLContext.get(sid),
            WebHITLContext.get(sid)
        )
        assert ctx1 is ctx2, "并发 get 应返回同一实例"
        print(f"[OK] 并发获取返回同一实例")

        await WebHITLContext.remove(sid)


# ============================================================================
# API 端点集成测试
# ============================================================================

class TestExcelExtractionAPI:
    """API 端点集成测试（需要运行中的服务器）"""

    BASE_URL = "http://localhost:8000/api/v1"
    _setup_done = False
    _headers = {}
    _client = None

    @classmethod
    def setup_class(cls):
        """测试类初始化 — 同步登录获取 token"""
        import httpx

        async def _setup():
            cls._client = httpx.AsyncClient(timeout=30.0)
            try:
                resp = await cls._client.post(
                    f"{cls.BASE_URL}/auth/login",
                    json={"username": "test", "password": "test123"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("access_token", "")
                    cls._headers = {"Authorization": f"Bearer {token}"}
                    print(f"\n[SETUP] 登录成功，token={token[:20]}...")
                else:
                    cls._headers = {}
                    print(f"\n[WARN] 登录失败: {resp.status_code}, {resp.text[:100]}")
            except Exception as e:
                cls._headers = {}
                print(f"\n[WARN] 无法连接服务器: {e}")
            cls._setup_done = True
            return cls

        asyncio.run(_setup())

    @classmethod
    def teardown_class(cls):
        """测试类清理"""
        if cls._client:
            async def _close():
                await cls._client.aclose()
            try:
                asyncio.run(_close())
            except Exception:
                pass

    @property
    def headers(self):
        return self._headers

    @property
    def client(self):
        return self._client

    def _skip_if_no_auth(self):
        if not self._headers:
            pytest.skip("未登录，跳过 API 测试")

    @pytest.mark.asyncio
    async def test_upload_endpoint(self):
        """测试文件上传端点"""
        self._skip_if_no_auth()

        excel_path = get_sample_excel_path()
        docx_path = get_sample_docx_path()

        files = []
        with open(excel_path, "rb") as f:
            files.append(("files", (os.path.basename(excel_path), f.read(), "application/vnd.ms-excel")))

        if docx_path and os.path.exists(docx_path):
            with open(docx_path, "rb") as f:
                files.append(("strategy_file", (os.path.basename(docx_path), f.read(),
                                                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document")))

        resp = await self.client.post(
            f"{self.BASE_URL}/excel-extraction/upload",
            headers=self.headers,
            files=files,
            timeout=30.0
        )

        assert resp.status_code == 200, f"上传失败: {resp.text}"
        data = resp.json()
        assert data.get("success") is True
        assert "session_id" in data
        assert "preview" in data

        preview = data["preview"]
        assert preview.get("row_count", 0) > 0
        print(f"[OK] 上传成功: session_id={data['session_id']}, "
              f"行数={preview['row_count']}, 列={preview['columns']}")

        return data

    @pytest.mark.asyncio
    async def test_create_and_list_task(self):
        """测试任务创建与列表查询"""
        self._skip_if_no_auth()

        # 先上传文件
        upload_data = await self.test_upload_endpoint()
        session_id = upload_data["session_id"]
        upload_dir = upload_data["preview"]["upload_dir"]

        # 创建任务
        resp = await self.client.post(
            f"{self.BASE_URL}/excel-extraction/tasks",
            headers={**self.headers, "Content-Type": "application/json"},
            json={
                "task_name": "自动化测试任务",
                "session_id": session_id,
                "config": {
                    "extract_fields": ["related", "institution", "summary"],
                    "max_concurrent": 3,
                    "enable_smart_hitl": True,
                },
                "upload_dir": upload_dir,
                "strategy_path": upload_data["preview"].get("strategy_path"),
            },
            timeout=30.0
        )

        assert resp.status_code == 200, f"创建任务失败: {resp.text}"
        data = resp.json()
        assert data.get("success") is True
        assert "task_id" in data
        print(f"[OK] 任务创建: task_id={data['task_id']}, status={data['status']}")

        # 查询任务列表
        resp = await self.client.get(
            f"{self.BASE_URL}/excel-extraction/tasks",
            headers=self.headers,
            params={"page": 1, "page_size": 5},
            timeout=30.0
        )

        assert resp.status_code == 200
        list_data = resp.json()
        assert "items" in list_data
        assert list_data["total"] >= 1
        print(f"[OK] 任务列表: {list_data['total']} 个任务")

        # 查询单个任务
        resp = await self.client.get(
            f"{self.BASE_URL}/excel-extraction/tasks/{data['task_id']}",
            headers=self.headers,
            timeout=30.0
        )

        assert resp.status_code == 200
        detail = resp.json()
        assert detail["task_id"] == data["task_id"]
        print(f"[OK] 任务详情: {detail['task_name']}, session_id={detail.get('session_id')}")

        return data


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-s", "--tb=short"])
