下面给你一个**清晰、可直接使用的 Python 异步（asyncio）+ logger 日志示例**，并解释常见的最佳实践。

---

# ✅ 基础版：Asyncio + logging

```python
import asyncio
import logging

# ---- 设置 logger ----
logger = logging.getLogger("my_async_logger")
logger.setLevel(logging.INFO)

# 输出到控制台
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)


# ---- 异步任务 ----
async def async_task(name, delay):
    logger.info(f"Task {name} start")
    await asyncio.sleep(delay)
    logger.info(f"Task {name} complete")
    return delay


async def main():
    logger.info("Main start")

    tasks = [
        asyncio.create_task(async_task("A", 1)),
        asyncio.create_task(async_task("B", 2)),
    ]

    results = await asyncio.gather(*tasks)
    logger.info(f"All tasks done, results = {results}")

    logger.info("Main complete")


asyncio.run(main())
```

---

# 📌 输出示例

```
2025-11-20 14:32:01 - my_async_logger - INFO - Main start
2025-11-20 14:32:01 - my_async_logger - INFO - Task A start
2025-11-20 14:32:01 - my_async_logger - INFO - Task B start
2025-11-20 14:32:02 - my_async_logger - INFO - Task A complete
2025-11-20 14:32:03 - my_async_logger - INFO - Task B complete
2025-11-20 14:32:03 - my_async_logger - INFO - All tasks done, results = [1, 2]
2025-11-20 14:32:03 - my_async_logger - INFO - Main complete
```

---

# ⭐ 推荐写法：为每个协程创建自己的 `logger`

```python
import asyncio
import logging

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

async def worker(id):
    log = get_logger(f"worker-{id}")
    log.info("start working")
    await asyncio.sleep(1)
    log.info("done working")

async def main():
    await asyncio.gather(*(worker(i) for i in range(3)))

asyncio.run(main())
```

每个 worker 会有自己的 log 前缀。

---

# 🔥 给你一个真实生产级日志方案（异步写文件）

可以把日志写入文件，同时兼容异步：

```python
import asyncio
import logging
from logging.handlers import RotatingFileHandler

# 按大小滚动日志
handler = RotatingFileHandler(
    "app.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
)
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
handler.setFormatter(formatter)

logger = logging.getLogger("async_app")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

async def job(i):
    logger.info(f"job {i} started")
    await asyncio.sleep(1)
    logger.info(f"job {i} finished")

async def main():
    await asyncio.gather(*(job(x) for x in range(5)))

asyncio.run(main())
```

---

# ❗注意事项（你一定用得到）

### 1. logger 自身是线程安全的

在 async 环境下直接用没问题，不会互相覆盖。

### 2. 不要重复添加 handler

否则会出现重复日志 → 用 `if not logger.handlers:` 防止重复绑定。

### 3. 大量日志建议配合队列（异步队列日志）

若你需要，我也能给你基于 `asyncio.Queue` 的异步日志 pipeline。

---

# 想进一步扩展吗？

我可以继续提供：

✔ async + logging + 异步 HTTP（aiohttp）示例
✔ 日志异步写入 + JSON 格式化（适合 ELK / Loki）
✔ FastAPI 中的 async logger 最佳实践
✔ 在 uvloop 环境下优化日志

你想要哪种？




下面给你**最清晰、可靠、可直接用的方案：在 Python 异步环境下把日志写入“不同文件”**。不同文件可以依据 **模块名、任务名、日期、类型** 等动态区分。

我分成几种常见需求给你示例👇

---

# ✅ 方案 1：不同任务写不同文件（最常用）

```python
import asyncio
import logging
from logging.handlers import RotatingFileHandler

def get_file_logger(name, filename):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 保证 handler 不重复绑定
    if not logger.handlers:
        handler = RotatingFileHandler(
            filename,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


async def worker(id):
    logger = get_file_logger(f"worker-{id}", f"worker_{id}.log")
    logger.info("Start")
    await asyncio.sleep(1)
    logger.info("End")


async def main():
    await asyncio.gather(*(worker(i) for i in range(3)))

asyncio.run(main())
```

运行后会生成：

```
worker_0.log
worker_1.log
worker_2.log
```

---

# ✅ 方案 2：按日志级别写入不同文件（如 info.log / error.log）

```python
import logging

logger = logging.getLogger("multi_file")
logger.setLevel(logging.DEBUG)

info_handler = logging.FileHandler("info.log", encoding="utf-8")
info_handler.setLevel(logging.INFO)

error_handler = logging.FileHandler("error.log", encoding="utf-8")
error_handler.setLevel(logging.ERROR)

fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
info_handler.setFormatter(fmt)
error_handler.setFormatter(fmt)

logger.addHandler(info_handler)
logger.addHandler(error_handler)

logger.info("This goes to info.log")
logger.error("This goes to error.log")
```

---

# ✅ 方案 3：按日期自动分文件（TimedRotatingFileHandler）

例如每天一个新文件：

```python
from logging.handlers import TimedRotatingFileHandler
import logging

def get_daily_logger(name, filename_prefix):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = TimedRotatingFileHandler(
            f"{filename_prefix}.log",
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8"
        )
        formatter = logging.Formatter("%(asctime)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

log = get_daily_logger("daily", "app")

log.info("Today’s log")
```

文件会变成：

```
app.log
app.log.2025-11-20
app.log.2025-11-21
...
```

---

# ✅ 方案 4：动态决定写入哪个文件（运行中切换）

适合按照内容分类：

```python
def get_dynamic_logger(category):
    logger = logging.getLogger(category)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.FileHandler(f"{category}.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        logger.addHandler(handler)

    return logger


def log_to(category, msg):
    logger = get_dynamic_logger(category)
    logger.info(msg)


log_to("trade", "buy order")
log_to("system", "startup ok")
log_to("trade", "sell order")
```

会生成：

```
trade.log
system.log
```

---

# 🔥 Bonus：异步 + 多文件日志最佳实践

如果你要在高并发 async 环境写日志，可以把日志写入异步队列：

```
asyncio → queue → writer task → 文件
```

可以避免磁盘 IO 阻塞运行。

如果你需要，我可以给你：

✔ 完整 async queue 日志系统
✔ FastAPI 项目中按用户 / 请求写不同文件
✔ 按天 + 按任务 + 按级别同时分文件

---

# 想问一下你是哪种需求？

1. 每个异步任务写自己的独立文件？
2. 按日志级别分文件？
3. 按日期轮转？
4. 根据内容动态分类？
5. 高性能异步写入多个日志文件？

告诉我你的使用场景，我给你定制化版本。
