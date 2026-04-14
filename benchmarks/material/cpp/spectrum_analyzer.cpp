#include "spectrum_analyzer.h"
#include <iostream>
#include <algorithm>
#include <cmath>
#include <numeric>
#include <functional>

namespace hajimi {

// ==================== 异常类实现 ====================

SpectrumError::SpectrumError(const std::string& msg)
    : std::runtime_error("[SpectrumError] " + msg) {}

GhostReadingError::GhostReadingError(const std::string& sensor_id, double reported_value)
    : SpectrumError("Ghost reading from sensor " + sensor_id +
                    ": " + std::to_string(reported_value)) {}

CalibrationError::CalibrationError(const std::string& reason)
    : SpectrumError("Calibration error: " + reason) {}

// ==================== Pimpl 实现 ====================

struct SpectrumAnalyzer::Impl {
    std::deque<HistoryEntry> history;
    double current_base_noise = 0.5;
    double base_noise_baseline = 0.5;
    std::map<std::string, double> calibration_offsets;

    // 回调
    AnomalyDetectedCallback on_anomaly_detected;
    CalibrationCompletedCallback on_calibration_completed;
};

// ==================== 构造/析构 ====================

SpectrumAnalyzer::SpectrumAnalyzer(int buffer_size)
    : pimpl_(std::make_unique<Impl>()), buffer_size_(buffer_size) {}

SpectrumAnalyzer::~SpectrumAnalyzer() = default;

SpectrumAnalyzer::SpectrumAnalyzer(SpectrumAnalyzer&& other) noexcept
    : pimpl_(std::move(other.pimpl_)), buffer_size_(other.buffer_size_) {}

SpectrumAnalyzer& SpectrumAnalyzer::operator=(SpectrumAnalyzer&& other) noexcept {
    if (this != &other) {
        pimpl_ = std::move(other.pimpl_);
        buffer_size_ = other.buffer_size_;
    }
    return *this;
}

// ==================== 频谱采样 ====================

void SpectrumAnalyzer::addSample(const SpectrumSample& sample) {
    if (!validateSample(sample)) {
        std::cerr << "[SpectrumAnalyzer] 采样点验证失败" << std::endl;
        return;
    }

    HistoryEntry entry;
    entry.sample = sample;
    entry.is_validated = true;

    pimpl_->history.push_back(std::move(entry));

    // 限制历史记录大小
    while (static_cast<int>(pimpl_->history.size()) > buffer_size_) {
        pimpl_->history.pop_front();
    }
}

void SpectrumAnalyzer::batchAddSamples(const std::vector<SpectrumSample>& samples) {
    for (const auto& sample : samples) {
        addSample(sample);
    }
}

bool SpectrumAnalyzer::validateSample(const SpectrumSample& sample) const {
    if (sample.sensor_id.empty()) {
        return false;
    }
    if (sample.amplitude < 0.0) {
        return false;
    }
    return true;
}

// ==================== 频谱分析 ====================

ResonancePeakAnalysis SpectrumAnalyzer::analyzeResonancePeak() const {
    if (pimpl_->history.empty()) {
        return ResonancePeakAnalysis{
            .center_frequency = 0.0,
            .bandwidth = 0.0,
            .peak_amplitude = 0.0,
            .is_within_ideal_range = false,
            .assessment = "No data"
        };
    }

    // 找到振幅最大的点作为共振峰
    auto max_it = std::max_element(pimpl_->history.begin(), pimpl_->history.end(),
        [](const HistoryEntry& a, const HistoryEntry& b) {
            return a.sample.amplitude < b.sample.amplitude;
        });

    double peak_freq = max_it->sample.frequency;
    double peak_amp = max_it->sample.amplitude;
    double peak_hum = max_it->sample.hum_level;

    // 计算带宽（振幅 > 50% 峰值的频率范围）
    double half_peak = peak_amp * 0.5;
    double min_freq = peak_freq;
    double max_freq = peak_freq;

    for (const auto& entry : pimpl_->history) {
        if (entry.sample.amplitude >= half_peak) {
            min_freq = std::min(min_freq, entry.sample.frequency);
            max_freq = std::max(max_freq, entry.sample.frequency);
        }
    }

    double bandwidth = max_freq - min_freq;

    // 判断是否在理想区间（共振峰区间）
    bool is_ideal = (peak_hum >= 40.0 && peak_hum <= 80.0);

    std::string assessment = is_ideal ? "共振峰正常" : "共振峰偏离理想区间";

    return ResonancePeakAnalysis{
        .center_frequency = peak_freq,
        .bandwidth = bandwidth,
        .peak_amplitude = peak_amp,
        .is_within_ideal_range = is_ideal,
        .assessment = assessment
    };
}

double SpectrumAnalyzer::calculateBaseNoise(int window_size) const {
    auto levels = extractHumLevels(window_size);
    if (levels.empty()) {
        return pimpl_->current_base_noise;
    }

    // 底噪取最小值
    double min_level = *std::min_element(levels.begin(), levels.end());

    // 更新当前底噪
    pimpl_->current_base_noise = min_level;
    return min_level;
}

double SpectrumAnalyzer::calculatePeakValley(int window_size) const {
    auto levels = extractHumLevels(window_size);
    if (levels.size() < 2) {
        return 0.0;
    }

    auto [min_it, max_it] = std::minmax_element(levels.begin(), levels.end());
    return *max_it - *min_it;
}

double SpectrumAnalyzer::getAverageHumLevel(int window_size) const {
    auto levels = extractHumLevels(window_size);
    if (levels.empty()) {
        return 0.0;
    }

    double sum = std::accumulate(levels.begin(), levels.end(), 0.0);
    return sum / levels.size();
}

std::vector<double> SpectrumAnalyzer::extractHumLevels(int count) const {
    std::vector<double> levels;
    int start_idx = std::max(0, static_cast<int>(pimpl_->history.size()) - count);

    for (size_t i = start_idx; i < pimpl_->history.size(); ++i) {
        levels.push_back(pimpl_->history[i].sample.hum_level);
    }

    return levels;
}

// ==================== 异常检测 ====================

AnomalyResult SpectrumAnalyzer::detectLatestAnomaly() const {
    AnomalyResult result;
    result.type = AnomalyType::None;
    result.severity = 0.0;
    result.detected_at = std::chrono::system_clock::now();

    if (pimpl_->history.size() < 2) {
        return result;
    }

    auto& latest = pimpl_->history.back();
    auto& previous = *(pimpl_->history.rbegin() + 1);

    // 检测毛刺
    double diff = std::abs(latest.sample.hum_level - previous.sample.hum_level);
    if (diff > spectrum_constants::SPIKE_THRESHOLD) {
        result.type = AnomalyType::Spike;
        result.severity = std::min(1.0, diff / (spectrum_constants::SPIKE_THRESHOLD * 2));
        result.description = "毛刺检测: 变化量 " + std::to_string(diff);
        result.sensor_id = latest.sample.sensor_id;
        result.reported_value = latest.sample.hum_level;
        result.corrected_value = previous.sample.hum_level;
    }

    // 检测底噪漂移
    if (isBaseNoiseDrifting()) {
        result.type = AnomalyType::BaselineDrift;
        result.severity = 0.6;
        result.description = "底噪漂移";
    }

    // 触发回调
    if (result.type != AnomalyType::None && pimpl_->on_anomaly_detected) {
        pimpl_->on_anomaly_detected(result);
    }

    return result;
}

bool SpectrumAnalyzer::detectGhostReading(const SpectrumSample& sample,
                                            const std::vector<SpectrumSample>& reference) {
    // 照妖镜 - 检测幽灵读数
    if (reference.empty()) {
        return false;
    }

    // 计算参考值的均值和标准差
    double sum = 0.0;
    for (const auto& ref : reference) {
        sum += ref.hum_level;
    }
    double mean = sum / reference.size();

    double variance = 0.0;
    for (const auto& ref : reference) {
        variance += std::pow(ref.hum_level - mean, 2);
    }
    double stddev = std::sqrt(variance / reference.size());

    // 如果采样值偏离均值超过 3 倍标准差，则为幽灵读数
    if (stddev > 0.0) {
        double z_score = std::abs(sample.hum_level - mean) / stddev;
        return z_score > 3.0;
    }

    // 标准差为 0 时，检查是否有明显差异
    return std::abs(sample.hum_level - mean) > spectrum_constants::SPIKE_THRESHOLD;
}

bool SpectrumAnalyzer::isSpike(double current, double previous) {
    return std::abs(current - previous) > spectrum_constants::SPIKE_THRESHOLD;
}

bool SpectrumAnalyzer::isBaseNoiseDrifting() const {
    double current_noise = calculateBaseNoise(50);
    double drift = std::abs(current_noise - pimpl_->base_noise_baseline);
    return drift > spectrum_constants::BASELINE_DRIFT_LIMIT;
}

// ==================== 历史记录 ====================

std::deque<HistoryEntry> SpectrumAnalyzer::getHistory(int count) const {
    int start_idx = std::max(0, static_cast<int>(pimpl_->history.size()) - count);
    return std::deque<HistoryEntry>(
        pimpl_->history.begin() + start_idx,
        pimpl_->history.end()
    );
}

std::vector<HistoryEntry> SpectrumAnalyzer::getHistoryByTimeRange(
    std::chrono::system_clock::time_point start,
    std::chrono::system_clock::time_point end) const {

    std::vector<HistoryEntry> result;
    for (const auto& entry : pimpl_->history) {
        if (entry.sample.timestamp >= start && entry.sample.timestamp <= end) {
            result.push_back(entry);
        }
    }
    return result;
}

// ==================== 校准 ====================

double SpectrumAnalyzer::calibrateFrequency(const std::string& resonator_id,
                                              double target_frequency) {
    // 定音鼓 - 校准谐振腔频率
    double current_freq = 0.0;

    // 查找该谐振腔的最新采样
    for (auto it = pimpl_->history.rbegin(); it != pimpl_->history.rend(); ++it) {
        if (it->sample.sensor_id == resonator_id) {
            current_freq = it->sample.frequency;
            break;
        }
    }

    double offset = target_frequency - current_freq;
    pimpl_->calibration_offsets[resonator_id] = offset;

    std::cout << "[SpectrumAnalyzer] 定音鼓校准: " << resonator_id
              << " 偏移 " << offset << std::endl;

    // 触发回调
    if (pimpl_->on_calibration_completed) {
        pimpl_->on_calibration_completed(true, offset);
    }

    return offset;
}

std::map<std::string, double> SpectrumAnalyzer::batchCalibrate(
    const std::map<std::string, double>& target_frequencies) {

    std::map<std::string, double> results;
    for (const auto& [resonator_id, target_freq] : target_frequencies) {
        results[resonator_id] = calibrateFrequency(resonator_id, target_freq);
    }
    return results;
}

// ==================== 叠韵 ====================

HarmonicResult SpectrumAnalyzer::executeHarmonic(const HarmonicConfig& config) {
    // 叠韵 - 多个谐振腔调至相同频率
    HarmonicResult result;
    result.success = true;

    auto start_time = std::chrono::steady_clock::now();

    for (const auto& resonator_id : config.resonator_ids) {
        double offset = calibrateFrequency(resonator_id, config.target_frequency);

        if (std::abs(offset) > config.tolerance) {
            result.success = false;
            result.error_message = "Resonator " + resonator_id + " out of tolerance";
            break;
        }

        result.achieved_frequencies[resonator_id] = config.target_frequency;
    }

    auto end_time = std::chrono::steady_clock::now();
    result.convergence_time_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        end_time - start_time).count();

    std::cout << "[SpectrumAnalyzer] 叠韵" << (result.success ? "成功" : "失败")
              << ": " << config.resonator_ids.size() << " 腔" << std::endl;

    return result;
}

// ==================== 回调注册 ====================

void SpectrumAnalyzer::onAnomalyDetected(AnomalyDetectedCallback cb) {
    pimpl_->on_anomaly_detected = std::move(cb);
}

void SpectrumAnalyzer::onCalibrationCompleted(CalibrationCompletedCallback cb) {
    pimpl_->on_calibration_completed = std::move(cb);
}

// ==================== 状态查询 ====================

size_t SpectrumAnalyzer::getSampleCount() const {
    return pimpl_->history.size();
}

bool SpectrumAnalyzer::isBaseNoiseStable() const {
    return !isBaseNoiseDrifting();
}

// ==================== 私有方法 ====================

double SpectrumAnalyzer::calculateStdDev(const std::vector<double>& values) const {
    if (values.size() < 2) {
        return 0.0;
    }

    double mean = std::accumulate(values.begin(), values.end(), 0.0) / values.size();
    double variance = 0.0;

    for (double v : values) {
        variance += std::pow(v - mean, 2);
    }

    return std::sqrt(variance / (values.size() - 1));
}

} // namespace hajimi
