"""打包入口。

本包包含预编译的原生扩展（``stockdb.pyd`` / ``zb_core.pyd``），它们链接
稳定 ABI ``python3.dll``，可在 Python 3.10+ 上运行。通过自定义命令：

* ``BinaryDistribution`` 令 ``has_ext_modules()`` 返回 ``True``，使 wheel
  不再被误判为纯 Python 的 ``py3-none-any``；
* ``BinaryWheel`` 设置 ``py_limited_api``，将产物打成 ``cp310-abi3-win_amd64``，
  使得同一 wheel 可被 Python 3.10 及更高版本安装。
"""

from setuptools import setup
from setuptools.dist import Distribution
from wheel.bdist_wheel import bdist_wheel


class BinaryDistribution(Distribution):
    """标记本发行包含原生扩展，强制生成平台相关 wheel。"""

    def has_ext_modules(self):
        return True


class BinaryWheel(bdist_wheel):
    """稳定 ABI wheel：``cp310-abi3-win_amd64``，兼容 Python 3.10+。"""

    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False
        self.py_limited_api = "cp310"


setup(
    distclass=BinaryDistribution,
    cmdclass={"bdist_wheel": BinaryWheel},
)
