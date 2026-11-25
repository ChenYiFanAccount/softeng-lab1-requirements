"""工程根包（`code/`）。

存在这个 ``__init__.py`` 的原因不是风格，而是**必须**：Python 标准库自带一个
名为 ``code`` 的模块（`code.InteractiveConsole`），如果本目录只是命名空间包，
``python -m unittest code.tests.test_tx`` 会解析到标准库的 ``code``，报
``module 'code' has no attribute 'tests'``。加一个常规包就能让 ``code/`` 在
``sys.path`` 首位的当前目录下胜出。
"""
