import assert from "node:assert/strict";
import test from "node:test";
import { matchesOption } from "../src/lib/select-search.ts";

test("source names match Vietnamese text with or without accents", () => {
  assert.equal(matchesOption("Hướng dẫn đăng ký cấp căn cước trực tuyến", "dang ky can cuoc"), true);
  assert.equal(matchesOption("Hướng dẫn đăng ký cấp căn cước trực tuyến", "căn cước"), true);
  assert.equal(matchesOption("Nghị định số 216/2026/NĐ-CP", "216 2026"), true);
  assert.equal(matchesOption("Luật xử lý vi phạm hành chính", "  LUAT   HANH CHINH "), true);
});

test("unmatched source names stay hidden and empty search shows all", () => {
  assert.equal(matchesOption("pv07", "pc08"), false);
  assert.equal(matchesOption("pv07", ""), true);
});
