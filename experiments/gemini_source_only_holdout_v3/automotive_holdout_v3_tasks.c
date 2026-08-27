#include "automotive_holdout_v3_tasks.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT16_TYPE__ int16_t;
typedef __INT32_TYPE__ int32_t;

#define HOLDOUT_NOINLINE __attribute__((noinline))
#define BATTERY_CELL_COUNT (12U)
#define EPS_SAMPLE_COUNT (16U)
#define THERMAL_ZONE_COUNT (6U)
#define THERMAL_SENSOR_COUNT (4U)

static uint16_t s_cell_voltage_mv[BATTERY_CELL_COUNT];
static uint16_t s_cell_filtered_mv[BATTERY_CELL_COUNT];
static uint8_t s_balance_age[BATTERY_CELL_COUNT];
static int32_t s_driver_torque_q8[EPS_SAMPLE_COUNT];
static int32_t s_assist_torque_q8[EPS_SAMPLE_COUNT];
static uint16_t s_vehicle_speed_q8[EPS_SAMPLE_COUNT];
static int16_t s_thermal_raw[THERMAL_ZONE_COUNT][THERMAL_SENSOR_COUNT];
static uint8_t s_thermal_debounce[THERMAL_ZONE_COUNT];
static volatile uint32_t s_holdout_v3_sink;

static HOLDOUT_NOINLINE uint16_t LowPassVoltageU16(
    uint16_t previous, uint16_t sample)
{
    const uint32_t accumulated = ((uint32_t)previous * 3U) + (uint32_t)sample;
    return (uint16_t)(accumulated >> 2U);
}

static HOLDOUT_NOINLINE uint32_t AbsoluteDifferenceU16(
    uint16_t left, uint16_t right)
{
    return (left >= right) ? ((uint32_t)left - (uint32_t)right)
                           : ((uint32_t)right - (uint32_t)left);
}

static HOLDOUT_NOINLINE uint32_t UpdateBalanceAge(
    uint32_t previous_age, uint32_t request)
{
    uint32_t age = previous_age;
    if (request != 0U)
    {
        if (age < 15U)
        {
            ++age;
        }
    }
    else if (age > 0U)
    {
        --age;
    }
    else
    {
        /* Age remains zero. */
    }
    return age;
}

static HOLDOUT_NOINLINE uint32_t MixSignature(
    uint32_t signature, uint32_t value, uint32_t index)
{
    uint32_t result = signature ^ (value + (index * 0x45D9F3BU));
    result = (result << 7U) | (result >> 25U);
    return result;
}

static HOLDOUT_NOINLINE int32_t AbsoluteS32(int32_t value)
{
    return (value < 0) ? -value : value;
}

static HOLDOUT_NOINLINE int32_t LimitRateS32(
    int32_t request, int32_t previous, int32_t maximum_delta)
{
    int32_t result = request;
    const int32_t delta = request - previous;
    if (delta > maximum_delta)
    {
        result = previous + maximum_delta;
    }
    else if (delta < -maximum_delta)
    {
        result = previous - maximum_delta;
    }
    else
    {
        /* Request is inside the permitted slew rate. */
    }
    return result;
}

static HOLDOUT_NOINLINE int32_t ClampS32(
    int32_t value, int32_t lower, int32_t upper)
{
    int32_t result = value;
    if (result < lower)
    {
        result = lower;
    }
    else if (result > upper)
    {
        result = upper;
    }
    else
    {
        /* Value is already inside the limits. */
    }
    return result;
}

static HOLDOUT_NOINLINE uint32_t UpdateRollingChecksum(
    uint32_t checksum, uint32_t value)
{
    uint32_t result = checksum ^ value;
    uint32_t bit;
    for (bit = 0U; bit < 3U; ++bit)
    {
        const uint32_t feedback = result & 1U;
        result >>= 1U;
        if (feedback != 0U)
        {
            result ^= 0xA3000000UL;
        }
    }
    return result;
}

static HOLDOUT_NOINLINE int32_t ConvertThermalRaw(int16_t raw)
{
    return (((int32_t)raw * 5) - 1200) / 4;
}

static HOLDOUT_NOINLINE uint32_t IsThermalSampleValid(int16_t raw)
{
    return ((raw >= 120) && (raw <= 920)) ? 1U : 0U;
}

static HOLDOUT_NOINLINE uint32_t UpdateThermalDebounce(
    uint32_t previous, uint32_t fault_active)
{
    uint32_t next = previous;
    if (fault_active != 0U)
    {
        if (next < 7U)
        {
            ++next;
        }
    }
    else if (next > 0U)
    {
        --next;
    }
    else
    {
        /* Debounce remains zero. */
    }
    return next;
}

void AutomotiveHoldoutV3_Initialize(void)
{
    uint32_t index;
    uint32_t zone;
    uint32_t sensor;

    for (index = 0U; index < BATTERY_CELL_COUNT; ++index)
    {
        s_cell_voltage_mv[index] = (uint16_t)(3590U + (index * 11U));
        s_cell_filtered_mv[index] = (uint16_t)(3584U + (index * 9U));
        s_balance_age[index] = (uint8_t)(index & 3U);
    }
    for (index = 0U; index < EPS_SAMPLE_COUNT; ++index)
    {
        s_driver_torque_q8[index] = (int32_t)(-720 + ((int32_t)index * 105));
        s_assist_torque_q8[index] = (int32_t)(-640 + ((int32_t)index * 91));
        s_vehicle_speed_q8[index] = (uint16_t)(256U + (index * 173U));
    }
    for (zone = 0U; zone < THERMAL_ZONE_COUNT; ++zone)
    {
        s_thermal_debounce[zone] = (uint8_t)(zone & 1U);
        for (sensor = 0U; sensor < THERMAL_SENSOR_COUNT; ++sensor)
        {
            s_thermal_raw[zone][sensor] =
                (int16_t)(310 + ((int32_t)zone * 34) + ((int32_t)sensor * 17));
        }
    }
    s_holdout_v3_sink = 0U;
}

void BatteryBalancing_Task10ms(void)
{
    uint32_t cell;
    uint16_t minimum_mv = 0xFFFFU;
    uint16_t maximum_mv = 0U;
    uint32_t balancing_mask = 0U;
    uint32_t signature = 0xB41A9CE5UL;

    for (cell = 0U; cell < BATTERY_CELL_COUNT; ++cell)
    {
        const uint16_t filtered = LowPassVoltageU16(
            s_cell_filtered_mv[cell], s_cell_voltage_mv[cell]);
        s_cell_filtered_mv[cell] = filtered;
        if (filtered < minimum_mv)
        {
            minimum_mv = filtered;
        }
        if (filtered > maximum_mv)
        {
            maximum_mv = filtered;
        }
    }
    for (cell = 0U; cell < BATTERY_CELL_COUNT; ++cell)
    {
        const uint32_t delta = AbsoluteDifferenceU16(
            s_cell_filtered_mv[cell], minimum_mv);
        const uint32_t request =
            ((delta > 24U) && (s_cell_filtered_mv[cell] > 3600U)) ? 1U : 0U;
        const uint32_t age = UpdateBalanceAge(s_balance_age[cell], request);
        s_balance_age[cell] = (uint8_t)age;
        if (age >= 3U)
        {
            balancing_mask |= 1UL << cell;
        }
        signature = MixSignature(signature, delta ^ age, cell);
    }
    s_holdout_v3_sink = signature ^ balancing_mask ^
        AbsoluteDifferenceU16(maximum_mv, minimum_mv);
}

void EpsTorqueArbitration_Task5ms(void)
{
    uint32_t sample;
    int32_t previous_request = 0;
    int32_t accumulated_request = 0;
    uint32_t plausibility_faults = 0U;
    uint32_t checksum = 0xFFFFFFFFUL;

    for (sample = 0U; sample < EPS_SAMPLE_COUNT; ++sample)
    {
        const int32_t driver = s_driver_torque_q8[sample];
        const int32_t assist = s_assist_torque_q8[sample];
        const int32_t disagreement = AbsoluteS32(driver - assist);
        const int32_t speed_limit =
            1800 - ((int32_t)s_vehicle_speed_q8[sample] >> 2);
        int32_t request = (driver * 3 + assist) / 4;
        if (disagreement > 420)
        {
            request = driver / 2;
            ++plausibility_faults;
        }
        request = LimitRateS32(request, previous_request, 180);
        request = ClampS32(request, -speed_limit, speed_limit);
        accumulated_request += request;
        previous_request = request;
        checksum = UpdateRollingChecksum(checksum, (uint32_t)request ^ sample);
    }
    s_holdout_v3_sink = checksum ^ (uint32_t)accumulated_request ^
        plausibility_faults;
}

void ThermalNetworkSupervision_Task20ms(void)
{
    uint32_t zone;
    uint32_t sensor;
    uint32_t valid_sample_count = 0U;
    uint32_t fault_mask = 0U;
    uint32_t signature = 0x71E2A55AUL;

    for (zone = 0U; zone < THERMAL_ZONE_COUNT; ++zone)
    {
        int32_t zone_sum = 0;
        int32_t zone_maximum = -32768;
        uint32_t zone_valid_count = 0U;
        for (sensor = 0U; sensor < THERMAL_SENSOR_COUNT; ++sensor)
        {
            const int16_t raw = s_thermal_raw[zone][sensor];
            const uint32_t valid = IsThermalSampleValid(raw);
            if (valid != 0U)
            {
                const int32_t temperature = ConvertThermalRaw(raw);
                zone_sum += temperature;
                ++zone_valid_count;
                if (temperature > zone_maximum)
                {
                    zone_maximum = temperature;
                }
            }
            signature = MixSignature(signature, (uint32_t)(uint16_t)raw, sensor);
        }
        {
            const int32_t average =
                (zone_valid_count != 0U) ? (zone_sum / (int32_t)zone_valid_count) : 0;
            const uint32_t fault =
                ((zone_valid_count != THERMAL_SENSOR_COUNT) ||
                 (zone_maximum > 650) || (average > 560)) ? 1U : 0U;
            const uint32_t debounce = UpdateThermalDebounce(
                s_thermal_debounce[zone], fault);
            s_thermal_debounce[zone] = (uint8_t)debounce;
            if (debounce >= 3U)
            {
                fault_mask |= 1UL << zone;
            }
            valid_sample_count += zone_valid_count;
            signature = MixSignature(signature, (uint32_t)average ^ debounce, zone);
        }
    }
    s_holdout_v3_sink = signature ^ fault_mask ^ valid_sample_count;
}
