#include "automotive_blind_v9_tasks.h"

#define CYLINDER_COUNT (4U)
#define INJECTOR_SAMPLE_COUNT (6U)
#define CONTACTOR_HISTORY_COUNT (10U)
#define WHEEL_COUNT (4U)

static volatile int16_t s_injector_samples[CYLINDER_COUNT][INJECTOR_SAMPLE_COUNT];
static volatile int16_t s_injector_correction[CYLINDER_COUNT];
static volatile uint16_t s_pack_voltage_history[CONTACTOR_HISTORY_COUNT];
static volatile uint16_t s_bus_voltage_history[CONTACTOR_HISTORY_COUNT];
static volatile uint8_t s_contactor_state;
static volatile uint8_t s_contactor_fault_counter;
static volatile int16_t s_wheel_slip[WHEEL_COUNT];
static volatile int16_t s_requested_wheel_torque[WHEEL_COUNT];
static volatile int16_t s_yaw_error;
static volatile int16_t s_driver_torque;
static volatile uint32_t s_blind_v9_sink;

__attribute__((noinline))
static uint16_t AbsDifferenceU16(uint16_t first, uint16_t second)
{
    return (first >= second) ? (uint16_t)(first - second) :
        (uint16_t)(second - first);
}

__attribute__((noinline))
static int16_t ClampS16(int32_t value, int16_t lower, int16_t upper)
{
    int32_t result = value;
    if (result < lower) { result = lower; }
    else if (result > upper) { result = upper; }
    else { /* Value is inside the permitted interval. */ }
    return (int16_t)result;
}

__attribute__((noinline))
static int16_t InjectorTrimFromWindow(const volatile int16_t *samples)
{
    uint32_t index;
    int32_t sum = 0;
    int16_t minimum = samples[0];
    int16_t maximum = samples[0];
    for (index = 0U; index < INJECTOR_SAMPLE_COUNT; ++index)
    {
        const int16_t value = samples[index];
        sum += value;
        if (value < minimum) { minimum = value; }
        if (value > maximum) { maximum = value; }
    }
    return ClampS16((sum - minimum - maximum) >> 2, -120, 120);
}

__attribute__((noinline))
static uint8_t CountVoltageMismatch(void)
{
    uint32_t index;
    uint8_t mismatch_count = 0U;
    for (index = 0U; index < CONTACTOR_HISTORY_COUNT; ++index)
    {
        const uint16_t delta = AbsDifferenceU16(
            s_pack_voltage_history[index], s_bus_voltage_history[index]);
        if (delta > 180U) { ++mismatch_count; }
    }
    return mismatch_count;
}

__attribute__((noinline))
static int16_t WheelTorqueLimit(int32_t request, int16_t slip)
{
    int32_t limit = 900;
    int32_t magnitude = slip;
    if (magnitude < 0) { magnitude = -magnitude; }
    if (magnitude > 140) { limit -= (magnitude - 140) << 1; }
    if (limit < 260) { limit = 260; }
    return ClampS16(request, (int16_t)-limit, (int16_t)limit);
}

void BlindV9_Initialize(uint32_t task_id)
{
    uint32_t first;
    uint32_t second;
    static const int16_t injector_seed[CYLINDER_COUNT][INJECTOR_SAMPLE_COUNT] = {
        {18, 25, -7, 31, 12, 42}, {-22, -9, 14, 37, 5, 28},
        {45, 11, -18, 24, 33, -4}, {8, 19, 27, -13, 36, 16}
    };
    static const uint16_t pack_seed[CONTACTOR_HISTORY_COUNT] =
        {3560U, 3570U, 3552U, 3581U, 3568U, 3574U, 3559U, 3586U, 3571U, 3563U};
    static const uint16_t bus_seed[CONTACTOR_HISTORY_COUNT] =
        {3280U, 3310U, 3372U, 3401U, 3428U, 3444U, 3459U, 3476U, 3481U, 3493U};
    static const int16_t slip_seed[WHEEL_COUNT] = {82, -176, 214, -63};
    (void)task_id;
    for (first = 0U; first < CYLINDER_COUNT; ++first)
    {
        for (second = 0U; second < INJECTOR_SAMPLE_COUNT; ++second)
        { s_injector_samples[first][second] = injector_seed[first][second]; }
        s_injector_correction[first] = 0;
    }
    for (first = 0U; first < CONTACTOR_HISTORY_COUNT; ++first)
    {
        s_pack_voltage_history[first] = pack_seed[first];
        s_bus_voltage_history[first] = bus_seed[first];
    }
    for (first = 0U; first < WHEEL_COUNT; ++first)
    {
        s_wheel_slip[first] = slip_seed[first];
        s_requested_wheel_torque[first] = 0;
    }
    s_contactor_state = 1U;
    s_contactor_fault_counter = 2U;
    s_yaw_error = 96;
    s_driver_torque = 640;
    s_blind_v9_sink = 0U;
}

void InjectorCylinderCorrection_Task5ms(void)
{
    uint32_t cylinder;
    int32_t checksum = 0;
    for (cylinder = 0U; cylinder < CYLINDER_COUNT; ++cylinder)
    {
        const int16_t trim = InjectorTrimFromWindow(s_injector_samples[cylinder]);
        s_injector_correction[cylinder] = trim;
        checksum += (int32_t)trim * (int32_t)(cylinder + 1U);
    }
    s_blind_v9_sink = (uint32_t)checksum;
}

void BatteryContactorDiagnostic_Task10ms(void)
{
    const uint8_t mismatch_count = CountVoltageMismatch();
    uint32_t status;
    if (s_contactor_state != 0U)
    {
        if (mismatch_count >= 6U)
        {
            if (s_contactor_fault_counter < 15U) { ++s_contactor_fault_counter; }
        }
        else if (s_contactor_fault_counter > 0U) { --s_contactor_fault_counter; }
        else { /* Counter remains clear. */ }
    }
    else { s_contactor_fault_counter = 0U; }
    status = ((uint32_t)s_contactor_state << 24U) |
        ((uint32_t)s_contactor_fault_counter << 8U) | mismatch_count;
    s_blind_v9_sink = status;
}

void TorqueVectoringAllocation_Task2ms(void)
{
    uint32_t wheel;
    int32_t checksum = 0;
    for (wheel = 0U; wheel < WHEEL_COUNT; ++wheel)
    {
        int32_t yaw_term = ((int32_t)s_yaw_error * (int32_t)(wheel + 1U)) >> 2;
        int32_t request = s_driver_torque;
        if ((wheel & 1U) == 0U) { request += yaw_term; }
        else { request -= yaw_term; }
        s_requested_wheel_torque[wheel] = WheelTorqueLimit(
            request, s_wheel_slip[wheel]);
        checksum ^= (int32_t)s_requested_wheel_torque[wheel] << (wheel * 3U);
    }
    s_blind_v9_sink = (uint32_t)checksum;
}
