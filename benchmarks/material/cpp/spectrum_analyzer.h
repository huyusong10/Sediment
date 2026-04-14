#pragma once

#include <memory>
#include <string>
#include <vector>
#include <optional>
#include <deque>
#include <stdexcept>
#include <chrono>
#include <functional>
#include <map>

namespace hajimi {

// ==================== 异常类 ====================

class SpectrumError : public std::runtime_error {
public:
    explicit SpectrumError(const std::string& msg);
};

class GhostReadingError : public SpectrumError {
public:
    explicit GhostReadingError(const std::string& sensor_id, double reported_value);
};

class CalibrationError : public SpectrumError {
public:
    explicit CalibrationError(const std::string& reason);
};

// ==================== 枚举定义 ====================

enum class AnomalyType {
    None,
    Spike,              // 毛刺 - 嗡鸣度瞬间异常
    GhostReading,       // 幽灵读数 - 虚假嗡鸣度读数
    BaselineDrift,      // 底噪漂移
    PeakValleyExcess    // 峰谷差超标
};

enum class AnalysisMode {
    RealTime,
    Historical,
    Predictive
};

// ==================== 常量定义 ====================

namespace spectrum_constants {
    constexpr int HISTORY_BUFFER_SIZE = 10000;
    constexpr double SPIKE_THRESHOLD = 10.0;           // 毛刺判定阈值
    constexpr double GHOST_CONFIDENCE_MIN = 0.85;      // 幽灵读数判定置信度
    constexpr double PEAK_VALLEY_WARNING = 15.0;       // 峰谷差警告值
    constexpr double BASELINE_DRIFT_LIMIT = 2.0;       // 底噪漂移限制
    constexpr double DRUM_CALIBRATION_TOLERANCE = 0.5; // 定音鼓校准容差
}

// ==================== 数据结构 ====================

/**
 * @brief 频谱采样点
 */
struct SpectrumSample {
    double frequency;
    double amplitude;
    double hum_level;                                   // 嗡鸣度
    std::chrono::system_clock::time_point timestamp;
    std::string sensor_id;
};

/**
 * @brief 异常检测结果
 */
struct AnomalyResult {
    AnomalyType type;
    double severity;                                    // 严重程度 0.0 ~ 1.0
    std::string description;
    std::chrono::system_clock::time_point detected_at;
    std::string sensor_id;
    double reported_value;
    double corrected_value;
};

/**
 * @brief 共振峰分析结果
 */
struct ResonancePeakAnalysis {
    double center_frequency;
    double bandwidth;
    double peak_amplitude;
    bool is_within_ideal_range;
    std::string assessment;
};

/**
 * @brief 历史记录条目
 */
struct HistoryEntry {
    SpectrumSample sample;
    std::vector<AnomalyResult> anomalies;
    bool is_validated;
};

/**
 * @brief 叠韵配置
 */
struct HarmonicConfig {
    std::vector<std::string> resonator_ids;            // 参与叠韵的谐振腔
    double target_frequency;
    double tolerance;
    std::chrono::milliseconds timeout;
};

/**
 * @brief 叠韵结果
 */
struct HarmonicResult {
    bool success;
    std::map<std::string, double> achieved_frequencies;
    double convergence_time_ms;
    std::string error_message;
};

// ==================== 回调类型 ====================

using AnomalyDetectedCallback = std::function<void(const AnomalyResult&)>;
using CalibrationCompletedCallback = std::function<void(bool success, double offset)>;

/**
 * @brief 频谱分析器
 *
 * 核心职责：
 * - 频谱分析：实时分析嗡鸣度频谱
 * - 异常检测：识别毛刺、幽灵读数等异常
 * - 历史记录：留声机记录嗡鸣度历史
 * - 定音鼓校准：校准谐振腔频率
 * - 叠韵：多个谐振腔调至相同频率
 */
class SpectrumAnalyzer {
public:
    explicit SpectrumAnalyzer(int buffer_size = spectrum_constants::HISTORY_BUFFER_SIZE);
    ~SpectrumAnalyzer();

    SpectrumAnalyzer(const SpectrumAnalyzer&) = delete;
    SpectrumAnalyzer& operator=(const SpectrumAnalyzer&) = delete;
    SpectrumAnalyzer(SpectrumAnalyzer&&) noexcept;
    SpectrumAnalyzer& operator=(SpectrumAnalyzer&&) noexcept;

    // ==================== 频谱采样 ====================

    /**
     * @brief 添加采样点
     */
    void addSample(const SpectrumSample& sample);

    /**
     * @brief 批量添加采样
     */
    void batchAddSamples(const std::vector<SpectrumSample>& samples);

    // ==================== 频谱分析 ====================

    /**
     * @brief 分析共振峰
     * @return 共振峰分析结果
     */
    ResonancePeakAnalysis analyzeResonancePeak() const;

    /**
     * @brief 计算底噪
     * @param window_size 窗口大小
     * @return 底噪水平
     */
    double calculateBaseNoise(int window_size = 100) const;

    /**
     * @brief 计算峰谷差
     * @param window_size 窗口大小
     * @return 峰谷差
     */
    double calculatePeakValley(int window_size = 100) const;

    /**
     * @brief 获取平均嗡鸣度
     */
    double getAverageHumLevel(int window_size = 50) const;

    // ==================== 异常检测 ====================

    /**
     * @brief 检测最新异常
     * @return 异常检测结果
     */
    AnomalyResult detectLatestAnomaly() const;

    /**
     * @brief 照妖镜 - 检测幽灵读数
     * @param sample 待验证采样
     * @return 是否为幽灵读数
     */
    static bool detectGhostReading(const SpectrumSample& sample,
                                    const std::vector<SpectrumSample>& reference);

    /**
     * @brief 检测毛刺
     * @param current 当前值
     * @param previous 前值
     * @return 是否为毛刺
     */
    static bool isSpike(double current, double previous);

    /**
     * @brief 检测底噪漂移
     */
    bool isBaseNoiseDrifting() const;

    // ==================== 历史记录 ====================

    /**
     * @brief 留声机 - 获取历史记录
     */
    std::deque<HistoryEntry> getHistory(int count = 100) const;

    /**
     * @brief 查找特定时间段的历史
     */
    std::vector<HistoryEntry> getHistoryByTimeRange(
        std::chrono::system_clock::time_point start,
        std::chrono::system_clock::time_point end) const;

    // ==================== 校准 ====================

    /**
     * @brief 定音鼓 - 校准谐振腔频率
     * @param resonator_id 谐振腔ID
     * @param target_frequency 目标频率
     * @return 校准偏移量
     */
    double calibrateFrequency(const std::string& resonator_id, double target_frequency);

    /**
     * @brief 批量校准
     */
    std::map<std::string, double> batchCalibrate(
        const std::map<std::string, double>& target_frequencies);

    // ==================== 叠韵 ====================

    /**
     * @brief 叠韵 - 多个谐振腔调至相同频率
     * @param config 叠韵配置
     * @return 叠韵结果
     */
    HarmonicResult executeHarmonic(const HarmonicConfig& config);

    // ==================== 回调注册 ====================

    void onAnomalyDetected(AnomalyDetectedCallback cb);
    void onCalibrationCompleted(CalibrationCompletedCallback cb);

    // ==================== 状态查询 ====================

    size_t getSampleCount() const;
    bool isBaseNoiseStable() const;

private:
    struct Impl;
    std::unique_ptr<Impl> pimpl_;
    int buffer_size_;

    bool validateSample(const SpectrumSample& sample) const;
    double calculateStdDev(const std::vector<double>& values) const;
    std::vector<double> extractHumLevels(int count) const;
};

} // namespace hajimi
