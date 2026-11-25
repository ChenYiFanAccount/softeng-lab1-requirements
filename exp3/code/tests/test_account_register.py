"""注册与账号校验（S7 整改新增 ``AccountService.check_available`` 的用例）。

这里不碰界面，只锁两件事：
- 手机号/密码的校验顺序与文案（422），
- ``check_available`` 与 ``register`` 共用同一套判断（注册页即时提示不会与真正
  注册给出不同结论）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))

try:  # 两种跑法都要成立（G2-R1-02）
    from code.tests import support
except ImportError:  # pragma: no cover - 包模式下的引导
    import support  # type: ignore[no-redef]

from app.application.account_service import AccountService
from app.domain.errors import ValidationError


class AccountRegisterTest(unittest.TestCase):
    """注册接口的校验与"手机号可用性"一致性。"""

    def setUp(self) -> None:
        self._ctx = support.temp_database()
        self.conn, _path = self._ctx.__enter__()
        self.service = AccountService(self.conn)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_手机号格式不对时拒绝注册(self) -> None:
        """11 位数字以外的手机号一律 422。"""
        with self.assertRaises(ValidationError) as caught:
            self.service.register("1380000", "Passw0rd!")
        self.assertEqual(caught.exception.http_status, 422)
        self.assertIn("手机号必须是 11 位数字", str(caught.exception))

    def test_密码过弱时拒绝注册(self) -> None:
        """少于 8 位、或只有字母没有数字，都拒绝。"""
        with self.assertRaises(ValidationError):
            self.service.register("13900000123", "abc1")
        with self.assertRaises(ValidationError):
            self.service.register("13900000123", "abcdefghij")

    def test_两次密码不一致时拒绝注册(self) -> None:
        """确认框与密码不一致直接拒绝，避免建出"以为设了 A 其实设了 B"的账号。"""
        with self.assertRaises(ValidationError):
            self.service.register("13900000123", "Passw0rd!", "Passw0rd?")

    def test_可用性检查与注册结论一致(self) -> None:
        """``check_available`` 通过则 ``register`` 必然能成；已存在则两者都给 422。"""
        self.service.check_available("13900000124")
        actor = self.service.register("13900000124", "Passw0rd!")
        self.assertEqual(actor.login_name, "13900000124")
        with self.assertRaises(ValidationError) as available:
            self.service.check_available("13900000124")
        with self.assertRaises(ValidationError) as repeated:
            self.service.register("13900000124", "Passw0rd!")
        self.assertEqual(str(available.exception), str(repeated.exception))


if __name__ == "__main__":
    unittest.main()
