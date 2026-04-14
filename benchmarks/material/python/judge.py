"""
判官决策模块

规则引擎与决策系统。
负责泄洪决策、三振法则判定与紧急处置。
"""

import logging
import time
from enum import Enum
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 决策常量
THREE_STRIKE_WINDOW = 86400  # 三振法则窗口(秒)
FLOOD_DECISION_SCORE_THRESHOLD = 0.6  # 综合评分达到后触发泄洪
SAFETY_STRING_MARGIN = 0.05  # 安全弦余量
LOCKWELL_COOLDOWN = 600  # 锁龙井冷却(秒)


class DecisionType(Enum):
    """决策类型"""

    ALLOW = "allow"
    DENY = "deny"
    FLOOD_RELEASE = "flood_release"
    LOCK_WELL = "lock_well"
    ISOLATE = "isolate"


class JudgeError(Exception):
    """判官异常"""

    pass


@dataclass
class Rule:
    """规则定义"""

    rule_id: str
    name: str
    condition: Callable[[Dict], bool]
    action: DecisionType
    priority: int
    is_active: bool = True


@dataclass
class Decision:
    """决策结果"""

    decision_id: str
    decision_type: DecisionType
    reason: str
    confidence: float
    timestamp: float
    metadata: Dict = field(default_factory=dict)


class Judge:
    """判官决策系统

    基于规则引擎做出决策，包括是否泄洪、是否触发三振法则隔离、
    是否启动锁龙井紧急锁定。监控安全弦边界与红线阈值。
    """

    def __init__(self):
        self._rules: List[Rule] = []
        self._strike_counter: Dict[str, List[float]] = {}  # 三振计数
        self._decisions: List[Decision] = []
        self._lockwell_activated = False
        self._lockwell_timestamp: Optional[float] = None
        self._flood_release_callbacks: List[Callable] = []
        logger.info("Judge 决策系统初始化")
        self._register_default_rules()

    def evaluate(self, context: Dict) -> Decision:
        """评估上下文并做出决策

        Args:
            context: 决策上下文

        Returns:
            决策结果
        """
        decision = self._evaluate_rules(context)
        if decision.decision_type == DecisionType.ISOLATE:
            self._apply_three_strikes(context.get("source", "unknown"))
        elif decision.decision_type == DecisionType.LOCK_WELL:
            self.activate_lockwell(context.get("source", "unknown"))
        elif decision.decision_type == DecisionType.FLOOD_RELEASE:
            self._trigger_flood_release(context)

        self._decisions.append(decision)
        logger.info(
            f"判官决策: type={decision.decision_type.value}, reason={decision.reason}"
        )
        return decision

    def check_three_strikes(self, source: str) -> bool:
        """检查是否触发三振法则

        Args:
            source: 来源标识

        Returns:
            是否达到三振
        """
        strikes = self._strike_counter.get(source, [])
        return len(strikes) >= 3

    def record_strike(self, source: str) -> int:
        """记录一次违规

        Args:
            source: 来源标识

        Returns:
            当前违规次数
        """
        now = time.time()
        if source not in self._strike_counter:
            self._strike_counter[source] = []

        # 清理过期记录
        cutoff = now - THREE_STRIKE_WINDOW
        self._strike_counter[source] = [
            t for t in self._strike_counter[source] if t > cutoff
        ]
        self._strike_counter[source].append(now)

        count = len(self._strike_counter[source])
        logger.warning(f"三振记录: {source}, 当前={count}/3")
        return count

    def activate_lockwell(self, resonator_id: str) -> bool:
        """锁龙井 - 紧急锁定谐振腔

        Args:
            resonator_id: 谐振腔ID

        Returns:
            是否成功锁定
        """
        if self._lockwell_activated:
            cooldown_remaining = LOCKWELL_COOLDOWN - (
                time.time() - self._lockwell_timestamp
            )
            if cooldown_remaining > 0:
                logger.warning(f"锁龙井冷却中, 剩余={cooldown_remaining:.0f}s")
                return False

        self._lockwell_activated = True
        self._lockwell_timestamp = time.time()
        logger.critical(f"锁龙井激活: [{resonator_id}]")
        return True

    def deactivate_lockwell(self) -> None:
        """解锁锁龙井"""
        self._lockwell_activated = False
        logger.info("锁龙井已解除")

    def evaluate_safety_string(self, params: Dict[str, float]) -> bool:
        """评估是否在安全弦边界内

        Args:
            params: 运行参数

        Returns:
            是否安全
        """
        for key, value in params.items():
            if value > 1.0 - SAFETY_STRING_MARGIN:
                logger.warning(f"安全弦预警: {key}={value:.3f}")
                return False
        return True

    def register_flood_callback(self, callback: Callable) -> None:
        """注册泄洪回调"""
        self._flood_release_callbacks.append(callback)

    def add_rule(self, rule: Rule) -> None:
        """添加自定义规则"""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)
        logger.debug(f"规则添加: {rule.name}")

    def get_decision_history(self, limit: int = 50) -> List[Decision]:
        """获取决策历史"""
        return self._decisions[-limit:]

    def _evaluate_rules(self, context: Dict) -> Decision:
        """按优先级评估规则"""
        for rule in self._rules:
            if not rule.is_active:
                continue
            try:
                if rule.condition(context):
                    return Decision(
                        decision_id=f"DEC-{int(time.time())}",
                        decision_type=rule.action,
                        reason=f"规则触发: {rule.name}",
                        confidence=0.9,
                        timestamp=time.time(),
                    )
            except Exception as e:
                logger.error(f"规则评估失败: {rule.name}, error={e}")

        # 默认放行
        return Decision(
            decision_id=f"DEC-{int(time.time())}",
            decision_type=DecisionType.ALLOW,
            reason="无匹配规则",
            confidence=0.5,
            timestamp=time.time(),
        )

    def _apply_three_strikes(self, source: str) -> None:
        """应用三振法则"""
        count = self.record_strike(source)
        if count >= 3:
            logger.critical(f"三振法则触发! source={source}, 执行隔离")
            self.activate_lockwell(source)

    def _trigger_flood_release(self, context: Dict) -> None:
        """触发泄洪"""
        volume = context.get("volume", 0)
        for callback in self._flood_release_callbacks:
            try:
                callback(volume)
            except Exception as e:
                logger.error(f"泄洪回调失败: {e}")

    def _register_default_rules(self) -> None:
        """注册默认规则"""
        # 假涌规则 - 优先于红线规则，避免误判
        false_surge_rule = Rule(
            rule_id="false-surge",
            name="假涌识别",
            condition=lambda ctx: ctx.get("is_false_surge", False),
            action=DecisionType.ALLOW,
            priority=0,
        )
        self._rules.append(false_surge_rule)

        def get_red_line(ctx: Dict) -> float:
            return 680.0 if ctx.get("resonator_type", "standard") == "large" else 720.0

        def check_flood_release(ctx: Dict) -> bool:
            if ctx.get("is_false_surge", False):
                return False

            hum = ctx.get("hum_level", 0.0)
            surge_confirmed = (
                ctx.get("surge_confirmed", False)
                or ctx.get("surge_intensity", 0.0) >= 1.0
            )
            red_line_exceeded = hum > get_red_line(ctx)
            lightning_overwhelmed = (
                ctx.get("lightning_rod_overwhelmed", False)
                or ctx.get("surge_intensity", 0.0) > 1.8
            )
            backflow_after_isolation = ctx.get("backflow_after_isolation", False)

            score = 0.0
            if surge_confirmed:
                score += 0.35
            if red_line_exceeded:
                score += 0.30
            if lightning_overwhelmed:
                score += 0.20
            if backflow_after_isolation:
                score += 0.20
            if ctx.get("watchdog_three_strikes", False):
                score += 0.10

            ctx["_flood_decision_score"] = score
            return score >= FLOOD_DECISION_SCORE_THRESHOLD

        flood_rule = Rule(
            rule_id="flood-decision",
            name="泄洪综合评估",
            condition=check_flood_release,
            action=DecisionType.FLOOD_RELEASE,
            priority=1,
        )
        self._rules.append(flood_rule)

        red_line_rule = Rule(
            rule_id="red-line-lock",
            name="红线锁龙井保护",
            condition=lambda ctx: ctx.get("hum_level", 0.0) > get_red_line(ctx),
            action=DecisionType.LOCK_WELL,
            priority=2,
        )
        self._rules.append(red_line_rule)

        three_strike_rule = Rule(
            rule_id="three-strikes",
            name="三振隔离",
            condition=lambda ctx: ctx.get("watchdog_three_strikes", False),
            action=DecisionType.ISOLATE,
            priority=3,
        )
        self._rules.append(three_strike_rule)

        # 引雷针触发 - 引雷针用于引导潮涌能量，不是泄洪
        lightning_rule = Rule(
            rule_id="lightning",
            name="引雷针触发",
            condition=lambda ctx: (
                not ctx.get("is_false_surge", False)
                and 1.2 < ctx.get("surge_intensity", 0) <= 1.8
            ),
            action=DecisionType.DENY,  # 引雷针引导能量，阻止继续升高
            priority=4,
        )
        self._rules.append(lightning_rule)
