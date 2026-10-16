/**
 * Một lượt đăng nhập đi qua nhiều trang (wiki → chatbot → wiki). Lượt được nhớ trong
 * sessionStorage để /login không chuyển qua lại vô hạn khi đăng nhập liên tục thất bại.
 */

const ROUND_KEY = "dw-login-round";
const ROUND_TTL_MS = 3 * 60_000;

export const MAX_LOGIN_HOPS = 4;

export type LoginRound = { at: number; hops: number };

export function readLoginRound(): LoginRound {
  try {
    const raw = JSON.parse(sessionStorage.getItem(ROUND_KEY) ?? "null");
    if (raw && typeof raw.at === "number" && Date.now() - raw.at < ROUND_TTL_MS) {
      return { at: raw.at, hops: Number(raw.hops) || 0 };
    }
  } catch {
    // sessionStorage bị chặn hoặc dữ liệu hỏng: bắt đầu lượt mới.
  }
  return { at: Date.now(), hops: 0 };
}

export function saveLoginRound(round: LoginRound): void {
  try {
    sessionStorage.setItem(ROUND_KEY, JSON.stringify(round));
  } catch {
    // Không lưu được thì giới hạn MAX_LOGIN_HOPS không áp dụng; luồng vẫn chạy.
  }
}

export function clearLoginRound(): void {
  try {
    sessionStorage.removeItem(ROUND_KEY);
  } catch {
    // ignore
  }
}
