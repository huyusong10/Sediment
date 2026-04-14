#include "burst_buffer.h"
#include <iostream>
#include <algorithm>
#include <cmath>
#include <numeric>

namespace hajimi {

// ==================== 异常类实现 ====================

BurstBufferError::BurstBufferError(const std::string& msg)
    : std::runtime_error("[BurstBufferError] " + msg) {}

OverflowError::OverflowError(double current, double capacity)
    : BurstBufferError("Buffer overflow: " + std::to_string(current) +
                       " > capacity " + std::to_string(capacity)) {}

FloodgateError::FloodgateError(const std::string& reason)
    : BurstBufferError("Floodgate error: " + reason) {}

// ==================== Pimpl 实现 ====================

struct BurstBuffer::Impl {
    std::deque<BufferEntry> entries;
    BufferState state = BufferState::Idle;
    double current_level = 0.0;
    double speckle_ratio = 0.0;
    std::vector<SurgeEvent> surge_history;
    std::chrono::system_clock::time_point last_flood_time;

    // 回调
    SurgeDetectedCallback on_surge_detected;
    FloodExecutedCallback on_flood_executed;
    ContaminationCallback on_contamination;
};

// ==================== 构造/析构 ====================

BurstBuffer::BurstBuffer(double capacity)
    : pimpl_(std::make_unique<Impl>()), capacity_(capacity) {
    pimpl_->last_flood_time = std::chrono::system_clock::now();
}

BurstBuffer::~BurstBuffer() = default;

BurstBuffer::BurstBuffer(BurstBuffer&& other) noexcept
    : pimpl_(std::move(other.pimpl_)), capacity_(other.capacity_) {}

BurstBuffer& BurstBuffer::operator=(BurstBuffer&& other) noexcept {
    if (this != &other) {
        pimpl_ = std::move(other.pimpl_);
        capacity_ = other.capacity_;
    }
    return *this;
}

// ==================== 缓冲操作 ====================

bool BurstBuffer::inject(double quantity, double purity, const std::string& source_id) {
    if (!validateInjection(quantity, purity)) {
        return false;
    }

    // 检查是否会溢出
    double new_level = pimpl_->current_level + quantity;
    if (new_level > capacity_) {
        std::cerr << "[BurstBuffer] 注入将导致溢出" << std::endl;
        return false;
    }

    BufferEntry entry;
    entry.quantity = quantity;
    entry.purity = purity;
    entry.source_id = source_id;
    entry.enqueued_at = std::chrono::system_clock::now();

    pimpl_->entries.push_back(std::move(entry));
    pimpl_->current_level = new_level;

    // 更新散斑比例
    updateSpeckleRatio();

    // 检查是否触发潮涌吸收状态
    double saturation = getSaturationRatio();
    if (saturation >= burst_constants::SURGE_TRIGGER_RATIO) {
        pimpl_->state = BufferState::Absorbing;
    }

    return true;
}

std::optional<BufferEntry> BurstBuffer::extract(double requested_quantity) {
    if (pimpl_->entries.empty() || pimpl_->current_level <= 0.0) {
        return std::nullopt;
    }

    // 提取最早进入的条目
    auto& entry = pimpl_->entries.front();
    if (entry.quantity >= requested_quantity) {
        entry.quantity -= requested_quantity;
        pimpl_->current_level -= requested_quantity;

        BufferEntry result = entry;
        result.quantity = requested_quantity;

        updateSpeckleRatio();
        return result;
    }

    // 条目数量不足，整个取出
    BufferEntry result = std::move(pimpl_->entries.front());
    pimpl_->entries.pop_front();
    pimpl_->current_level -= result.quantity;

    updateSpeckleRatio();
    return result;
}

BufferSnapshot BurstBuffer::getSnapshot() const {
    return BufferSnapshot{
        .state = pimpl_->state,
        .current_level = pimpl_->current_level,
        .capacity = capacity_,
        .saturation_ratio = getSaturationRatio(),
        .speckle_ratio = pimpl_->speckle_ratio,
        .entry_count = pimpl_->entries.size()
    };
}

bool BurstBuffer::validateInjection(double quantity, double purity) const {
    if (quantity <= 0.0) {
        std::cerr << "[BurstBuffer] 注入量必须为正数" << std::endl;
        return false;
    }
    if (purity < 0.0 || purity > 1.0) {
        std::cerr << "[BurstBuffer] 纯度必须在 [0, 1] 范围内" << std::endl;
        return false;
    }
    if (pimpl_->state == BufferState::Contaminated) {
        std::cerr << "[BurstBuffer] 缓冲区已污染，拒绝注入" << std::endl;
        return false;
    }
    return true;
}

// ==================== 潮涌处理 ====================

bool BurstBuffer::absorbSurge(double surge_intensity) {
    // 引雷针 - 引导潮涌能量进入缓冲
    double available_capacity = capacity_ - pimpl_->current_level;

    if (surge_intensity > available_capacity) {
        std::cerr << "[BurstBuffer] 潮涌强度超出缓冲容量" << std::endl;
        pimpl_->state = BufferState::Full;
        return false;
    }

    pimpl_->current_level += surge_intensity;
    pimpl_->state = BufferState::Absorbing;

    std::cout << "[BurstBuffer] 引雷针吸收潮涌: " << surge_intensity << std::endl;

    // 触发回调
    if (pimpl_->on_surge_detected) {
        SurgeEvent event;
        event.peak_intensity = surge_intensity;
        event.start_time = std::chrono::system_clock::now();
        event.is_false_surge = false;
        pimpl_->on_surge_detected(event);
    }

    return true;
}

bool BurstBuffer::isFalseSurge(double reported_intensity, double sensor_reliability) {
    // 假涌 - 设备故障误报潮涌
    // 如果传感器可信度低且报告强度异常高，则可能是假涌
    if (sensor_reliability < 0.5 && reported_intensity > burst_constants::DEFAULT_CAPACITY * 0.8) {
        return true;
    }
    return false;
}

void BurstBuffer::recordSurgeEvent(const SurgeEvent& event) {
    pimpl_->surge_history.push_back(event);

    // 保留最近 100 条记录
    if (pimpl_->surge_history.size() > 100) {
        pimpl_->surge_history.erase(pimpl_->surge_history.begin());
    }
}

// ==================== 泄洪管理 ====================

FloodDecision BurstBuffer::evaluateFloodNeed() const {
    // 判官决策 - 是否需要泄洪
    double saturation = getSaturationRatio();

    if (saturation >= burst_constants::FLOOD_THRESHOLD_RATIO) {
        return FloodDecision::ExecuteFlood;
    } else if (saturation >= burst_constants::SURGE_TRIGGER_RATIO) {
        return FloodDecision::PrepareFlood;
    } else if (saturation >= 0.5) {
        return FloodDecision::Warning;
    }

    return FloodDecision::NoAction;
}

FloodReport BurstBuffer::executeFlood(double target_quantity) {
    FloodReport report;
    report.flood_time = std::chrono::system_clock::now();
    report.decision_reason = "Manual flood request";

    double actual_release = std::min(target_quantity, pimpl_->current_level);

    if (actual_release <= 0.0) {
        report.completed = false;
        report.released_quantity = 0.0;
        report.duration_seconds = 0.0;
        report.decision_reason = "No content to release";
        return report;
    }

    pimpl_->current_level -= actual_release;
    pimpl_->state = BufferState::Draining;

    // 移除相应条目
    double remaining = actual_release;
    while (remaining > 0.0 && !pimpl_->entries.empty()) {
        auto& entry = pimpl_->entries.front();
        if (entry.quantity <= remaining) {
            remaining -= entry.quantity;
            pimpl_->entries.pop_front();
        } else {
            entry.quantity -= remaining;
            remaining = 0.0;
        }
    }

    report.released_quantity = actual_release;
    report.duration_seconds = calculateFloodDuration(actual_release);
    report.completed = true;

    pimpl_->last_flood_time = std::chrono::system_clock::now();
    updateSpeckleRatio();

    std::cout << "[BurstBuffer] 泄洪完成: 释放 " << actual_release << std::endl;

    // 触发回调
    if (pimpl_->on_flood_executed) {
        pimpl_->on_flood_executed(report);
    }

    return report;
}

FloodReport BurstBuffer::emergencyFlood() {
    // 紧急泄洪 - 全速释放
    std::cout << "[BurstBuffer] 紧急泄洪启动!" << std::endl;
    return executeFlood(pimpl_->current_level);
}

double BurstBuffer::calculateFloodDuration(double quantity) const {
    // 泄洪持续时间与释放量成正比
    return quantity / (capacity_ * burst_constants::FLOOD_RATE);
}

// ==================== 污染防护 ====================

double BurstBuffer::reflectSpeckle(double speckle_ratio) {
    // 八卦镜 - 反射散斑污染
    // 假设八卦镜可以消除 70% 的散斑
    constexpr double REFLECTION_EFFICIENCY = 0.7;
    double reduced = speckle_ratio * (1.0 - REFLECTION_EFFICIENCY);

    std::cout << "[BurstBuffer] 八卦镜反射散斑: " << speckle_ratio
              << " -> " << reduced << std::endl;

    return reduced;
}

bool BurstBuffer::isContaminated() const {
    return pimpl_->speckle_ratio > burst_constants::MAX_SPECKLE_TOLERANCE;
}

void BurstBuffer::updateSpeckleRatio() {
    if (pimpl_->entries.empty()) {
        pimpl_->speckle_ratio = 0.0;
        return;
    }

    double total_purity = 0.0;
    for (const auto& entry : pimpl_->entries) {
        total_purity += (1.0 - entry.purity);
    }
    pimpl_->speckle_ratio = total_purity / pimpl_->entries.size();

    // 检查是否污染
    if (isContaminated() && pimpl_->state != BufferState::Contaminated) {
        pimpl_->state = BufferState::Contaminated;
        if (pimpl_->on_contamination) {
            pimpl_->on_contamination(pimpl_->speckle_ratio);
        }
    }
}

// ==================== 分流/合流 ====================

std::vector<BufferEntry> BurstBuffer::splitToTargets(int target_count, double per_target_quantity) {
    std::vector<BufferEntry> results;
    double total_needed = per_target_quantity * target_count;

    if (pimpl_->current_level < total_needed) {
        std::cerr << "[BurstBuffer] 缓冲量不足，无法分流" << std::endl;
        return results;
    }

    for (int i = 0; i < target_count; ++i) {
        auto entry = extract(per_target_quantity);
        if (entry.has_value()) {
            results.push_back(std::move(entry.value()));
        }
    }

    std::cout << "[BurstBuffer] 分流完成: " << results.size() << " 路" << std::endl;
    return results;
}

bool BurstBuffer::mergeFromSources(const std::vector<BufferEntry>& sources) {
    double total_quantity = 0.0;

    for (const auto& source : sources) {
        total_quantity += source.quantity;
    }

    if (pimpl_->current_level + total_quantity > capacity_) {
        std::cerr << "[BurstBuffer] 合流将导致溢出" << std::endl;
        return false;
    }

    for (const auto& source : sources) {
        pimpl_->entries.push_back(source);
    }
    pimpl_->current_level += total_quantity;

    updateSpeckleRatio();
    std::cout << "[BurstBuffer] 合流完成: " << total_quantity << std::endl;
    return true;
}

// ==================== 回调注册 ====================

void BurstBuffer::onSurgeDetected(SurgeDetectedCallback cb) {
    pimpl_->on_surge_detected = std::move(cb);
}

void BurstBuffer::onFloodExecuted(FloodExecutedCallback cb) {
    pimpl_->on_flood_executed = std::move(cb);
}

void BurstBuffer::onContamination(ContaminationCallback cb) {
    pimpl_->on_contamination = std::move(cb);
}

// ==================== 属性访问 ====================

double BurstBuffer::getCurrentLevel() const {
    return pimpl_->current_level;
}

double BurstBuffer::getSaturationRatio() const {
    if (capacity_ <= 0.0) return 0.0;
    return pimpl_->current_level / capacity_;
}

} // namespace hajimi
