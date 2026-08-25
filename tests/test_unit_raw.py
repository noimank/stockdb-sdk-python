"""离线单元测试：RdClient / Pipeline 的参数折叠与转发行为。"""

import asyncio

from stockdb_sdk import Pipeline, RdClient


class _Doable:
    """模拟原生 len() 返回的需 .do() 物化的包装。"""

    def __init__(self, value):
        self._value = value

    def do(self):
        return self._value


class RecordingNative:
    """记录每次调用参数与返回值的最小原生替身。"""

    def __init__(self):
        self.calls = []

    def _record(self, name, args):
        self.calls.append((name, args))
        return f"<{name}-result>"

    def get(self, *a): return self._record("get", a)
    def vals(self, *a): return self._record("vals", a)
    def mget(self, *a): return self._record("mget", a)
    def delete(self, *a): return self._record("delete", a)
    def set(self, *a): return self._record("set", a)
    def setl(self, *a): return self._record("setl", a)
    def setr(self, *a): return self._record("setr", a)
    def mset(self, *a): return self._record("mset", a)

    def keys(self, *a):
        self._record("keys", a)
        return ["<key-1>", "<key-2>"]

    def len(self, *a):
        self._record("len", a)
        return _Doable(7)

    def pipe(self):
        self._record("pipe", ())
        return RecordingPipe()

    def close(self): self._record("close", ())
    def send(self, m): return self._record("send", (m,))
    def send_sync(self, m): return self._record("send_sync", (m,))


class RecordingPipe:
    def __init__(self):
        self.calls = []

    def mget(self, *a):
        self.calls.append(("mget", a))
        return self

    def mset(self, *a):
        self.calls.append(("mset", a))
        return self

    def do(self):
        return ["<pipe-result>"]

    def __await__(self):
        async def _coro():
            return ["<pipe-await-result>"]
        return _coro().__await__()


# ---------- 读方法的键参数折叠 ----------

def test_read_key_arg_folding():
    native = RecordingNative()
    rd = RdClient(native)

    assert rd.get("日k") == "<get-result>"
    assert rd.get("日k", "600633") == "<get-result>"
    rd.get("日k", "600633", "20260625")
    rd.vals("退市*")
    rd.vals("日k", "600633", "2026062*")
    rd.mget("日k", "600633", "20260625")
    rd.delete("mydb", "*")

    assert native.calls == [
        ("get", ("日k",)),
        ("get", ("日k", "600633")),
        ("get", ("日k", "600633", "20260625")),
        ("vals", ("退市*",)),
        ("vals", ("日k", "600633", "2026062*")),
        ("mget", ("日k", "600633", "20260625")),
        ("delete", ("mydb", "*")),
    ]


def test_keys_len_key_arg_folding():
    native = RecordingNative()
    rd = RdClient(native)

    assert rd.keys("退市*") == ["<key-1>", "<key-2>"]  # 物化为纯 list
    assert rd.len("日k", "600633", "202606*") == 7     # 物化为纯 int
    rd.keys("日k", "600633")
    rd.keys("日k", "600633", "202606*")
    rd.len("日k")

    assert native.calls == [
        ("keys", ("退市*",)),
        ("len", ("日k", "600633", "202606*")),
        ("keys", ("日k", "600633")),
        ("keys", ("日k", "600633", "202606*")),
        ("len", ("日k",)),
    ]


# ---------- 写方法按参数个数透传 ----------

def test_write_passthrough_by_arity():
    native = RecordingNative()
    rd = RdClient(native)

    rd.set("mydb", {"v": 1})
    rd.set("mydb", "k", ["a"])
    rd.set("mydb", "k", "k2", 123)
    rd.setl("mydb", "k", "L")
    rd.setr("mydb", "k", "R")
    rd.mset("mydb", "k", "k2", 9)

    assert native.calls == [
        ("set", ("mydb", {"v": 1})),
        ("set", ("mydb", "k", ["a"])),
        ("set", ("mydb", "k", "k2", 123)),
        ("setl", ("mydb", "k", "L")),
        ("setr", ("mydb", "k", "R")),
        ("mset", ("mydb", "k", "k2", 9)),
    ]


# ---------- 管线 ----------

def test_pipeline_queue_and_do():
    native = RecordingNative()
    rd = RdClient(native)

    pp = rd.pipe()
    assert isinstance(pp, Pipeline)
    ret = pp.mget("日k", "600633", "20260625").mset("mydb", "k", 1)
    assert ret is pp  # 链式返回自身
    assert pp.do() == ["<pipe-result>"]
    assert native.calls == [("pipe", ())]
    assert pp._native.calls == [
        ("mget", ("日k", "600633", "20260625")),
        ("mset", ("mydb", "k", 1)),
    ]


def test_pipeline_awaitable():
    rd = RdClient(RecordingNative())
    pp = rd.pipe()
    assert asyncio.run(_await(pp)) == ["<pipe-await-result>"]


async def _await(obj):
    return await obj


# ---------- 连接与底层 ----------

def test_close_send_forwarding():
    native = RecordingNative()
    rd = RdClient(native)

    rd.close()
    rd.send(b"frame")
    rd.send_sync(b"frame")

    assert native.calls == [
        ("close", ()),
        ("send", (b"frame",)),
        ("send_sync", (b"frame",)),
    ]
