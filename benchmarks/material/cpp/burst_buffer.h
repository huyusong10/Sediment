#pragma once

#include <memory>
#include <string>
#include <vector>
#include <optional>
#include <deque>
#include <stdexcept>
#include <chrono>
#include <functional>

namespace hajimi {

// ==================== 异常类 ====================

class BurstBufferError : public std::runtime_error {
public:
    explicit BurstBufferError(const std::string& msg);
};

class OverflowError : public BurstBufferError {
public:
    explicit OverflowError(double current, double capacity);
};

class FloodgateError : public BurstBufferError {
public:
    explicit FloodgateError(const std::string& reason);
};

// ==================== 枚举定义 ====================

enum class BufferState {
    Idle,
    Absorbing,      // 吸收潮涌中
    Draining,       // 泄洪中
    Full,
    Contaminated    // 被散斑污染
};

enum class FloodDecision {
    NoAction,
    Warning,
    PrepareFlood,   // 准备泄洪
    ExecuteFlood    // 执行泄洪
};

// ==================== 常量定义 ====================

namespace burst_constants {
    constexpr double DEFAULT_CAPACITY = 1000.0;
    constexpr double SURGE_TRIGGER_RATIO = 0.7;       // 潮涌触发比例
    constexpr double FLOOD_THRESHOLD_RATIO = 0.85;    // 泄洪阈值
    constexpr double FLOOD_RATE = 0.3;                // 泄洪速率（每秒释放比例）
    constexpr double MAX_SPECKLE_TOLERANCE = 0.1;     // 最大散斑容忍度
    constexpr double DRAIN_STEP = 50.0;               // 每次泄洪步长
}

// ==================== 数据结构 ====================

/**
 * @brief 缓冲条目
 */
struct BufferEntry {
    double quantity;
    double purity;
    std::chrono::system_clock::time_point enqueued_at;
    std::string source_id;
};

/**
 * @brief 潮涌事件
 */
struct SurgeEvent {
    std::string event_id;
    double peak_intensity;
    std::chrono::system_clock::time_point start_time;
    std::chrono::system_clock::time_point end_time;
    bool is_false_surge;                              // 假涌标记
};

/**
 * @brief 泄洪报告
 */
struct FloodReport {
    double released_quantity;
    double duration_seconds;
    std::string decision_reason;
    bool completed;
    std::chrono::system_clock::time_point flood_time;
};

/**
 * @brief 缓冲状态快照
 */
struct BufferSnapshot {
    BufferState state;
    double current_level;
    double capacity;
    double saturation_ratio;
    double speckle_ratio;
    size_t entry_count;
};

// ==================== 回调类型 ====================

using SurgeDetectedCallback = std::function<void(const SurgeEvent&)>;
using FloodExecutedCallback = std::function<void(const FloodReport&)>;
using ContaminationCallback = std::function<void(double speckle_ratio)>;

/**
 * @brief 突发缓冲管理器
 *
 * 核心职责：
 * - 潮涌吸收：使用引雷针引导潮涌能量
 * - 泄洪管理：判官决策后紧急释放
 * - 污染防护：八卦镜反射散斑污染
 * - 假涌识别：检测设备故障误报
 * - 分流/合流：与驿站协调
 */
class BurstBuffer {
public:
    explicit BurstBuffer(double capacity = burst_constants::DEFAULT_CAPACITY);
    ~BurstBuffer();

    BurstBuffer(const BurstBuffer&) = delete;
    BurstBuffer& operator=(const BurstBuffer&) = delete;
    BurstBuffer(BurstBuffer&&) noexcept;
    BurstBuffer& operator=(BurstBuffer&&) noexcept;

    // ==================== 缓冲操作 ====================

    /**
     * @brief 注入哈基米到缓冲区
     */
    bool inject(double quantity, double purity, const std::string& source_id);

    /**
     * @brief 从缓冲区提取
     */
    std::optional<BufferEntry> extract(double requested_quantity);

    /**
     * @brief 获取当前缓冲状态
     */
    BufferSnapshot getSnapshot() const;

    // ==================== 潮涌处理 ====================

    /**
     * @brief 引雷针 - 引导潮涌能量进入缓冲
     * @param surge_intensity 潮涌强度
     * @return 是否成功吸收
     */
    bool absorbSurge(double surge_intensity);

    /**
     * @brief 检测假涌 - 设备故障误报潮涌
     * @param reported_intensity 报告的潮涌强度
     * @param sensor_reliability 传感器可信度
     * @return 是否为假涌
     */
    static bool isFalseSurge(double reported_intensity, double sensor_reliability);

    /**
     * @brief 记录潮涌事件
     */
    void recordSurgeEvent(const SurgeEvent& event);

    // ==================== 泄洪管理 ====================

    /**
     * @brief 判官决策 - 是否需要泄洪
     * @return 泄洪决策
     */
    FloodDecision evaluateFloodNeed() const;

    /**
     * @brief 执行泄洪
     * @param target_quantity 目标释放量
     * @return 泄洪报告
     */
    FloodReport executeFlood(double target_quantity);

    /**
     * @brief 紧急泄洪 - 全速释放
     */
    FloodReport emergencyFlood();

    // ==================== 污染防护 ====================

    /**
     * @brief 八卦镜 - 反射散斑污染
     * @param speckle_ratio 当前散斑比例
     * @return 净化后的散斑比例
     */
    double reflectSpeckle(double speckle_ratio);

    /**
     * @brief 检查污染状态
     */
    bool isContaminated() const;

    // ==================== 分流/合流 ====================

    /**
     * @brief 分流到多个目标
     */
    std::vector<BufferEntry> splitToTargets(int target_count, double per_target_quantity);

    /**
     * @brief 合流多个来源
     */
    bool mergeFromSources(const std::vector<BufferEntry>& sources);

    // ==================== 回调注册 ====================

    void onSurgeDetected(SurgeDetectedCallback cb);
    void onFloodExecuted(FloodExecutedCallback cb);
    void onContamination(ContaminationCallback cb);

    // ==================== 属性访问 ====================

    double getCapacity() const { return capacity_; }
    double getCurrentLevel() const;
    double getSaturationRatio() const;

private:
    struct Impl;
    std::unique_ptr<Impl> pimpl_;
    double capacity_;

    bool validateInjection(double quantity, double purity) const;
    void updateSpeckleRatio();
    double calculateFloodDuration(double quantity) const;
};

} // namespace hajimi
