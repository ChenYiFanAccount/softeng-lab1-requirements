"""事务封装三件套（S1-6）：自动提交模式、`BEGIN IMMEDIATE` 前置 DML 不炸、并发不互相踩。

P0 第 1 轮评审抓到的原始缺陷是：``sqlite3`` 默认 ``isolation_level=''`` 会在第一条
DML 前隐式开事务，之后 ``BEGIN IMMEDIATE`` 抛 ``cannot start a transaction within a
transaction``。这里既断言"能跑通"，也断言"工厂确实关了驱动的隐式事务"。
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import unittest

try:  # 跑法一：python -m unittest code.tests.test_x
    from code.tests import support
except ImportError:  # pragma: no cover - 跑法二：discover -s code/tests -t code
    import support  # type: ignore[no-redef]

from app.infrastructure.db.connection import immediate_transaction


class TransactionTest(unittest.TestCase):
    """连接工厂与写事务的行为契约。"""

    def setUp(self) -> None:
        self._stack = contextlib.ExitStack()
        self.conn, self.db_path = self._stack.enter_context(support.temp_database())
        self.fixture = support.insert_fixture(self.conn)
        # 可售给足 400，让并发用例能加到 200 而不撞 占用 <= 可售 的行内约束
        support.insert_inventory(self.conn, self.fixture["room_type_id"], "2027-03-01", 400, 0)

    def tearDown(self) -> None:
        self._stack.close()

    def test_immediate_after_dml_does_not_raise(self) -> None:
        """先 DML（自动提交）再 ``BEGIN IMMEDIATE`` 不得抛「事务内开事务」。"""
        self.conn.execute(
            "UPDATE room_inventory SET occupied_rooms = 1 WHERE room_type_id = ?",
            (self.fixture["room_type_id"],),
        )
        try:
            with immediate_transaction(self.conn):
                self.conn.execute(
                    "UPDATE room_inventory SET occupied_rooms = occupied_rooms + 1"
                    " WHERE room_type_id = ?",
                    (self.fixture["room_type_id"],),
                )
        except sqlite3.OperationalError as error:  # pragma: no cover - 失败时才走
            self.fail(f"BEGIN IMMEDIATE 不应抛异常：{error}")
        occupied = self.conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ?",
            (self.fixture["room_type_id"],),
        ).fetchone()[0]
        self.assertEqual(occupied, 2)

    def test_driver_autocommit_is_disabled(self) -> None:
        """连接处于 ``isolation_level=None``（自动提交），事务边界由我们控制。"""
        self.assertIsNone(self.conn.isolation_level)
        self.assertFalse(self.conn.in_transaction)

    def test_busy_timeout_is_explicit(self) -> None:
        """``busy_timeout`` 显式设置，锁冲突时等待重试而不是立刻 ``database is locked``。"""
        timeout = self.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertGreaterEqual(int(timeout), 1000)

    def test_foreign_keys_on_every_connection(self) -> None:
        """每新建的连接都开外键（SQLite 默认是关的，漏一处就等于没约束）。"""
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_rollback_on_exception(self) -> None:
        """事务体内抛异常时整批回滚，占用不会被改脏。"""
        with self.assertRaises(RuntimeError):
            with immediate_transaction(self.conn):
                self.conn.execute(
                    "UPDATE room_inventory SET occupied_rooms = 4 WHERE room_type_id = ?",
                    (self.fixture["room_type_id"],),
                )
                raise RuntimeError("模拟业务失败")
        occupied = self.conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ?",
            (self.fixture["room_type_id"],),
        ).fetchone()[0]
        self.assertEqual(occupied, 0)

    def test_nested_transaction_is_rejected(self) -> None:
        """嵌套事务被显式拒绝，避免静默把内层当外层的一部分提交。"""
        with immediate_transaction(self.conn):
            with self.assertRaises(RuntimeError):
                with immediate_transaction(self.conn):
                    pass

    def test_concurrent_writers_serialize(self) -> None:
        """8 线程各 +1、各 25 轮：总占用必须是 200，且没有一次 ``database is locked``。"""
        room_type_id = self.fixture["room_type_id"]
        errors: list[str] = []
        start = threading.Barrier(8)

        def worker() -> None:
            conn = sqlite3.connect(str(self.db_path))
            conn.isolation_level = None
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            try:
                start.wait()
                for _ in range(25):
                    with immediate_transaction(conn):
                        conn.execute(
                            "UPDATE room_inventory"
                            " SET occupied_rooms = occupied_rooms + 1"
                            " WHERE room_type_id = ?",
                            (room_type_id,),
                        )
            except Exception as error:  # pylint: disable=broad-exception-caught
                # 线程内异常必须全量兜住并带回主线程断言，否则并发问题会静默消失。
                errors.append(f"{type(error).__name__}: {error}")
            finally:
                conn.close()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(errors, [])
        occupied = self.conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ?",
            (room_type_id,),
        ).fetchone()[0]
        self.assertEqual(occupied, 200)


if __name__ == "__main__":
    unittest.main()
