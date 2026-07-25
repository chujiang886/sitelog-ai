"""T14-1：PDF 方案书生成端点测试。

验证 ``POST /api/report/generate``：
- 正常 dossier → 200、Content-Type 含 application/pdf、body 以 b"%PDF" 开头；
- 某段为 None（如 vision=None）→ 仍返回合法 PDF（generator 兜底）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _mock_dossier() -> dict:
    """构造与三个 Agent 真实 data 字段形态一致的 dossier。"""

    return {
        "project": {
            "address": "广东省汕头市龙湖区某某小区 3 栋 1801",
            "request_id": "REQ-20250721-0001",
        },
        "vision": {
            "scene_type": "开放阳台",
            "obstructions": ["空调外机", "晾衣架", "护栏"],
            "orientation_hint": "东南",
            "quality": "high",
            "recommendations": ["建议封装以提升保温性能"],
            "pending_verification": True,
            "gaps": ["vision_model: pending_verification"],
        },
        "environment": {
            "climate_zone": "夏热冬暖地区",
            "prevailing_wind": "东南",
            "solar_exposure": "西晒明显",
            "noise_level_hint": "中",
            "regulatory_hints": ["阳台封装需符合地方管理条例"],
            "regional_material_preference": "断桥铝为主",
            "summary": "华南沿海高温高湿、台风频发，需重视隔热与抗风压。",
            "pending_verification": True,
        },
        "design": {
            "candidates": [
                {
                    "id": "D1",
                    "title": "断桥铝平开窗方案",
                    "opening_type": "平开窗",
                    "frame_material": "断桥铝合金",
                    "glass_type": "中空 Low-E 玻璃",
                    "dimensions_hint": "主窗 1.8m×2.1m，分 2 扇",
                    "estimated_cost_tier": "标准",
                    "pros": ["密封性好", "保温隔热佳", "抗风压能力强"],
                    "cons": ["开启占用室内空间", "五金成本略高"],
                    "rationale": "结合西晒与台风区，断桥铝 + Low-E 兼顾隔热与气密。",
                },
            ],
            "pending_verification": False,
            "gaps": [],
        },
    }


client = TestClient(app)


def test_generate_report_returns_valid_pdf() -> None:
    """正常 dossier 返回合法 PDF 字节流。"""

    resp = client.post("/api/report/generate", json=_mock_dossier())
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers.get("content-type", "")
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) > 200


def test_generate_report_with_none_section_still_valid() -> None:
    """vision=None 时仍返回合法 PDF（generator 兜底，不抛）。"""

    dossier = _mock_dossier()
    dossier["vision"] = None
    resp = client.post("/api/report/generate", json=dossier)
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers.get("content-type", "")
    assert resp.content.startswith(b"%PDF")


def test_generate_report_all_sections_none_still_valid() -> None:
    """三段全部为 None → 仍返回合法 PDF（generator 全段兜底，不抛）。"""

    dossier = {
        "project": {"address": "广东省汕头市龙湖区某某小区 3 栋 1801"},
        "vision": None,
        "environment": None,
        "design": None,
    }
    resp = client.post("/api/report/generate", json=dossier)
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers.get("content-type", "")
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) > 200


def test_generate_report_minimal_empty_body_still_valid() -> None:
    """请求体为空 dict（缺省 project={} 且三段 None）→ 仍返回合法 PDF。"""

    resp = client.post("/api/report/generate", json={})
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers.get("content-type", "")
    assert resp.content.startswith(b"%PDF")
