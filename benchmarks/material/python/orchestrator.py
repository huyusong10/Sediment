"""
千机匣编排模块

自动化控制系统的任务调度与流程编排。
管理晨祷、晚课日常流程，协调看门狗与判官。
"""

import logging
import time
from enum import Enum
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

# 编排常量
MAX_CONCURRENT_TASKS = 10  # 最大并发任务数
TASK_TIMEOUT = 300  # 任务超时(秒)
RETRY_MAX_ATTEMPTS = 3  # 最大重试次数
MORNING_PRAYER_INTERVAL = 86400  # 晨祷间隔(秒)
EVENING_CLASS_INTERVAL = 86400  # 晚课间隔(秒)


class TaskStatus(Enum):
    """任务状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Priority(Enum):
    """优先级"""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class OrchestratorError(Exception):
    """编排器异常"""

    pass


@dataclass
class Task:
    """任务定义"""

    task_id: str
    name: str
    handler: Callable
    priority: Priority
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None


class Orchestrator:
    """千机匣自动化编排器

    负责任务调度、流程编排与异常处理。
    管理晨祷(启动检查)、晚课(数据归档)等日常流程，
    协调看门狗监控与判官决策。
    """

    def __init__(self, name: str = "千机匣"):
        self.name = name
        self._task_queue: List[Task] = []
        self._task_registry: Dict[str, Task] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TASKS)
        self._running = False
        self._morning_prayer_registered = False
        self._evening_class_registered = False
        logger.info(f"{self.name} 初始化完成")

    def register_task(self, task: Task) -> None:
        """注册任务"""
        with self._lock:
            self._task_registry[task.task_id] = task
            self._insert_by_priority(task)
        logger.debug(f"任务注册: {task.name} (优先级={task.priority.value})")

    def submit_morning_prayer(self, handler: Callable) -> None:
        """注册晨祷流程 - 每日系统启动检查

        Args:
            handler: 晨祷处理函数
        """
        task = Task(
            task_id="morning-prayer",
            name="晨祷",
            handler=handler,
            priority=Priority.CRITICAL,
        )
        self.register_task(task)
        self._morning_prayer_registered = True
        logger.info("晨祷流程已注册")

    def submit_evening_class(self, handler: Callable) -> None:
        """注册晚课流程 - 每日关闭前数据归档

        Args:
            handler: 晚课处理函数
        """
        task = Task(
            task_id="evening-class",
            name="晚课",
            handler=handler,
            priority=Priority.HIGH,
        )
        self.register_task(task)
        self._evening_class_registered = True
        logger.info("晚课流程已注册")

    def execute_task(self, task_id: str) -> Any:
        """执行单个任务

        Args:
            task_id: 任务ID

        Returns:
            任务执行结果
        """
        task = self._task_registry.get(task_id)
        if not task:
            raise OrchestratorError(f"任务不存在: {task_id}")

        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        logger.info(f"执行任务: {task.name}")

        try:
            result = task.handler(*task.args, **task.kwargs)
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            logger.info(
                f"任务完成: {task.name}, 耗时={task.completed_at - task.started_at:.1f}s"
            )
            return result
        except Exception as e:
            task.error = str(e)
            task.retry_count += 1
            if task.retry_count < RETRY_MAX_ATTEMPTS:
                logger.warning(
                    f"任务失败, 重试 ({task.retry_count}/{RETRY_MAX_ATTEMPTS}): {task.name}"
                )
                task.status = TaskStatus.PENDING
                return self.execute_task(task_id)
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            logger.error(f"任务失败: {task.name}, error={e}")
            raise

    def execute_pipeline(self, task_ids: List[str]) -> Dict[str, Any]:
        """执行任务流水线

        Args:
            task_ids: 按顺序执行的任务ID列表

        Returns:
            各任务执行结果
        """
        results = {}
        for task_id in task_ids:
            try:
                results[task_id] = self.execute_task(task_id)
            except Exception as e:
                results[task_id] = {"error": str(e)}
                logger.error(f"流水线中断: {task_id}")
                # 通知看门狗记录三振
                self._notify_watchdog(task_id, str(e))
                break
        return results

    def trigger_cleanup(self, handler: Callable) -> None:
        """触发清道夫任务"""
        task = Task(
            task_id=f"cleanup-{int(time.time())}",
            name="清道夫",
            handler=handler,
            priority=Priority.NORMAL,
        )
        self.register_task(task)
        self.execute_task(task.task_id)

    def trigger_repair(self, handler: Callable) -> None:
        """触发补天任务"""
        task = Task(
            task_id=f"repair-{int(time.time())}",
            name="补天",
            handler=handler,
            priority=Priority.CRITICAL,
        )
        self.register_task(task)
        self.execute_task(task.task_id)

    def schedule_coating_replacement(self, handler: Callable) -> None:
        """调度换羽任务"""
        task = Task(
            task_id=f"coating-replace-{int(time.time())}",
            name="换羽",
            handler=handler,
            priority=Priority.LOW,
        )
        self.register_task(task)

    def set_initial_parameters(self, handler: Callable) -> None:
        """点睛 - 注入初始参数"""
        logger.info("点睛流程启动")
        result = handler()
        logger.info(f"点睛完成: {result}")

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        task = self._task_registry.get(task_id)
        return task.status if task else None

    def shutdown(self) -> None:
        """关闭编排器"""
        self._running = False
        self._executor.shutdown(wait=True)
        logger.info(f"{self.name} 已关闭")

    def _insert_by_priority(self, task: Task) -> None:
        """按优先级插入任务队列"""
        for i, existing in enumerate(self._task_queue):
            if task.priority.value < existing.priority.value:
                self._task_queue.insert(i, task)
                return
        self._task_queue.append(task)

    def _notify_watchdog(self, task_id: str, error: str) -> None:
        """通知看门狗"""
        logger.warning(f"[看门狗] 任务失败: {task_id}, {error}")
        # TODO: 未完成，待实现实际环境触发看门狗计数器
