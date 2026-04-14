#pragma once

#include <memory>
#include <string>
#include <vector>
#include <optional>
#include <stdexcept>
#include <chrono>

namespace hajimi {

// ==================== 异常类 ====================

/**
 * @brief 谐振腔操作异常
 */
class ResonatorError : public std::runtime_error {
public:
    explicit ResonatorError(const std::string& msg);
};

/**
 * @brief 状态转换异常 - 非法状态迁移
 */
class StateTransitionError : public ResonatorError {
public:
    explicit StateTransitionError(const std::string& from, const std::string& to);
};

/**
 * @brief 饱和度过高异常
 */
class SaturationOverflowError : public ResonatorError {
public:
    explicit SaturationOverflowError(double current, double limit);
};

// ==================== 枚举定义 ====================

/**
 * @brief 谐振腔运行状态
 */
enum class ResonatorState {
    Silent,       // 静默态 - 无哈基米流动
    Warm,         // 温存 - 维持最低嗡鸣度待机
    Running,      // 运行态 - 正常工作
    Collapsing,   // 坍缩中 - 谐振腔失效导致哈基米释放
    Sealed,       // 封窖 - 长期存储休眠模式
    HotStandby    // 热备份 - 随时可接管的副本
};

/**
 * @brief 健康等级
 */
enum class HealthLevel {
    Excellent,    // 溢彩 - 镀层完好
    Good,
    Warning,      // 晦暗 - 镀层老化
    Critical,     // 接近红线
    Dead          // 已坍缩
};

// ==================== 常量定义 ====================

namespace constants {
    constexpr double DEFAULT_RED_LINE = 720.0;           // 红线 - 嗡鸣度不可超过的阈值 (标准腔, Hz体系)
    constexpr double LARGE_CAVITY_RED_LINE = 680.0;      // 红线 - 大型腔阈值 (Hz体系)
    constexpr double RESONANCE_PEAK_MIN = 420.0;         // 共振峰下限 (Hz体系)
    constexpr double RESONANCE_PEAK_MAX = 580.0;         // 共振峰上限 (Hz体系)
    constexpr double MAX_SATURATION = 85.0;             // 最大饱和度 (百分比)
    constexpr double SATURATION_WARNING = 70.0;          // 饱和度预警阈值
    constexpr double SATURATION_EMERGENCY = 95.0;        // 饱和度紧急阈值
    constexpr double WARM_HUM_THRESHOLD = 120.0;         // 温存态最低嗡鸣度 (Hz体系)
    constexpr double COLLAPSE_THRESHOLD = 800.0;         // 坍缩触发阈值 (Hz体系)
    constexpr int MAX_RETRY_COUNT = 3;                  // 三振法则重试次数
    constexpr double BASE_NOISE = 100.0;                 // 底噪基准值 (Hz体系)
    constexpr double DEFAULT_CAPACITY = 5000.0;          // 默认容量
}

// ==================== 配置结构体 ====================

/**
 * @brief 谐振腔配置参数
 */
struct ResonatorConfig {
    double red_line = constants::DEFAULT_RED_LINE;
    double resonance_peak_min = constants::RESONANCE_PEAK_MIN;
    double resonance_peak_max = constants::RESONANCE_PEAK_MAX;
    double max_saturation = constants::MAX_SATURATION;
    double warm_hum_threshold = constants::WARM_HUM_THRESHOLD;
    int max_retry_count = constants::MAX_RETRY_COUNT;
    bool enable_hot_standby = true;                     // 启用热备份
    std::string resonator_id;                           // 谐振腔唯一标识
};

/**
 * @brief 状态快照
 */
struct StateSnapshot {
    ResonatorState state;
    double hum_level;                                   // 嗡鸣度
    double saturation;                                  // 饱和度
    HealthLevel health;
    std::chrono::system_clock::time_point timestamp;
    std::string last_operation;
};

// ==================== 回调类型 ====================

using StateChangeCallback = std::function<void(ResonatorState old_state, ResonatorState new_state)>;
using CollapseWarningCallback = std::function<void(double hum_level, double threshold)>;

/**
 * @brief 谐振腔核心控制类
 *
 * 管理谐振腔的完整生命周期：
 * - 开光：新谐振腔首次启用
 * - 试音：测试谐振腔是否可用
 * - 状态监控：实时追踪嗡鸣度和饱和度
 * - 金蝉脱壳：故障腔无损迁移到热备份
 * - 封窖：长期存储哈基米的休眠模式
 */
class ResonatorCore {
public:
    explicit ResonatorCore(const ResonatorConfig& config);
    ~ResonatorCore();

    // 禁止拷贝，允许移动
    ResonatorCore(const ResonatorCore&) = delete;
    ResonatorCore& operator=(const ResonatorCore&) = delete;
    ResonatorCore(ResonatorCore&&) noexcept;
    ResonatorCore& operator=(ResonatorCore&&) noexcept;

    // ==================== 生命周期管理 ====================

    /**
     * @brief 开光 - 新谐振腔首次启用
     * @return 是否成功
     */
    bool tryConsecration();

    /**
     * @brief 试音 - 测试谐振腔是否可用
     * @return 试音结果
     */
    bool trySoundTest();

    /**
     * @brief 启动到运行态
     */
    bool tryStartup();

    /**
     * @brief 关闭到静默态
     */
    bool tryShutdown();

    /**
     * @brief 封窖 - 进入长期存储休眠模式
     */
    bool trySeal();

    /**
     * @brief 破窖 - 从封窖状态恢复
     */
    bool tryUnseal();

    // ==================== 状态查询 ====================

    ResonatorState getState() const;
    StateSnapshot getSnapshot() const;
    double getHumLevel() const;               // 获取当前嗡鸣度
    double getSaturation() const;             // 获取饱和度
    HealthLevel getHealthLevel() const;
    bool isHealthy() const;
    bool isAtRedLine() const;                 // 是否触及红线
    bool isInResonancePeak() const;           // 嗡鸣度是否在共振峰区间

    // ==================== 状态转换 ====================

    /**
     * @brief 切换到温存态 - 维持最低嗡鸣度待机
     */
    bool tryEnterWarm();

    /**
     * @brief 切换到热备份状态
     */
    bool tryEnterHotStandby();

    /**
     * @brief 接管热备份
     */
    bool takeOverStandby(ResonatorCore& standby);

    // ==================== 故障恢复 ====================

    /**
     * @brief 金蝉脱壳 - 故障腔无损迁移到热备份
     * @param target 目标热备份谐振腔
     * @return 迁移是否成功
     */
    bool executeGoldenShell(ResonatorCore& target);

    /**
     * @brief 触发坍缩流程
     */
    bool triggerCollapse();

    /**
     * @brief 紧急锁定 - 锁龙井机制
     */
    bool emergencyLock();

    // ==================== 回调注册 ====================

    void onStateChange(StateChangeCallback cb);
    void onCollapseWarning(CollapseWarningCallback cb);

    // ==================== 属性访问 ====================

    const std::string& getId() const { return config_.resonator_id; }
    const ResonatorConfig& getConfig() const { return config_; }

private:
    struct Impl;
    std::unique_ptr<Impl> pimpl_;
    ResonatorConfig config_;

    bool validateStateTransition(ResonatorState from, ResonatorState to) const;
    void notifyStateChange(ResonatorState old_state, ResonatorState new_state);
    void checkCollapseRisk();
};

} // namespace hajimi
