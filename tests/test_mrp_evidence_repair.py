from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai.mrp import writer


@pytest.mark.asyncio
async def test_corrective_pass_uses_source_over_bad_plan_identifier():
    llm = SimpleNamespace(generate=AsyncMock(return_value="Theo Nghị định 168/2024/NĐ-CP."))
    source = "Nghị định 238/2026/NĐ-CP sửa Nghị định 168/2024/NĐ-CP."
    original = "Theo Nghị định 100/2019/NĐ-CP."
    result = await writer.repair_evidence(llm, original, source, source)
    assert result == "Theo Nghị định 168/2024/NĐ-CP."
    assert source in llm.generate.await_args.args[0]
    assert "missing_source_reference" in llm.generate.await_args.args[0]
    llm.generate.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate", ["Theo Nghị định 999/2026/NĐ-CP.", "", "Text[^missing]"])
async def test_corrective_pass_keeps_failed_draft_blocked_if_still_invalid(candidate):
    llm = SimpleNamespace(generate=AsyncMock(return_value=candidate))
    original = "Theo Nghị định 100/2019/NĐ-CP."
    result = await writer.repair_evidence(llm, original, "168/2024/NĐ-CP", "168/2024/NĐ-CP")
    assert result == original
    llm.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_good_draft_does_not_spend_repair_call():
    llm = SimpleNamespace(generate=AsyncMock())
    assert await writer.repair_evidence(llm, "Nội dung đúng.", "Nội dung đúng.", "Nội dung đúng.") == "Nội dung đúng."
    llm.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_must_not_destroy_existing_table_rows():
    table = "\n\n| Mục | Giá trị |\n| --- | --- |\n" + "".join(f"| {x} | 1 |\n" for x in "ABCDE")
    original = "Theo Nghị định 100/2019/NĐ-CP." + table
    llm = SimpleNamespace(generate=AsyncMock(return_value="Theo Nghị định 168/2024/NĐ-CP."))
    assert await writer.repair_evidence(llm, original, "168/2024/NĐ-CP" + table, "168/2024/NĐ-CP" + table) == original


@pytest.mark.asyncio
async def test_repair_cannot_drop_even_one_supported_table_row():
    table = "\n\n| Mục | Giá trị |\n| --- | --- |\n" + "".join(f"| {x} | 1 |\n" for x in "ABCDE")
    original = "Theo Nghị định 100/2019/NĐ-CP." + table
    candidate = original.replace("100/2019", "168/2024").replace("| E | 1 |\n", "")
    llm = SimpleNamespace(generate=AsyncMock(return_value=candidate))
    assert await writer.repair_evidence(llm, original, "168/2024/NĐ-CP" + table, "168/2024/NĐ-CP" + table) == original


@pytest.mark.asyncio
async def test_repair_cannot_replace_draft_with_short_summary():
    original = "Theo Nghị định 100/2019/NĐ-CP. " + "Nội dung cần giữ. " * 80
    candidate = "Theo Nghị định 168/2024/NĐ-CP. " + "Nội dung cần giữ. " * 50
    llm = SimpleNamespace(generate=AsyncMock(return_value=candidate))
    assert await writer.repair_evidence(llm, original, "168/2024/NĐ-CP", "168/2024/NĐ-CP") == original
