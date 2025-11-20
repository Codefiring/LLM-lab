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
