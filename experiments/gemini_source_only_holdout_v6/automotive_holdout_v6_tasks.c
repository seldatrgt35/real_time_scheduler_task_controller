#include "automotive_holdout_v6_tasks.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT16_TYPE__ int16_t;
typedef __INT32_TYPE__ int32_t;

#define CELL_COUNT              (10U)
#define STEERING_SENSOR_COUNT   (3U)
#define STEERING_SAMPLE_COUNT   (5U)
#define GATEWAY_SIGNAL_COUNT    (8U)

static volatile uint16_t s_cell_voltage_mv[CELL_COUNT];
static volatile uint16_t s_cell_loaded_mv[CELL_COUNT];
static volatile uint16_t s_cell_current_ma[CELL_COUNT];
static volatile uint16_t s_cell_temperature[CELL_COUNT];
static volatile int16_t s_steering_samples[STEERING_SENSOR_COUNT]
                                                  [STEERING_SAMPLE_COUNT];
static volatile uint16_t s_steering_limit[STEERING_SENSOR_COUNT];
static volatile uint8_t s_gateway_alive[GATEWAY_SIGNAL_COUNT];
static volatile uint8_t s_gateway_previous_alive[GATEWAY_SIGNAL_COUNT];
static volatile uint8_t s_gateway_age[GATEWAY_SIGNAL_COUNT];
static volatile uint16_t s_gateway_value[GATEWAY_SIGNAL_COUNT];
static volatile uint8_t s_gateway_state;
static volatile uint32_t s_holdout_v6_sink;

static uint16_t AbsDiffU16(uint16_t left, uint16_t right)
{
    return (left >= right) ? (uint16_t)(left - right)
                           : (uint16_t)(right - left);
}

static uint16_t CellImpedanceU16(uint16_t open_mv,
                                uint16_t loaded_mv,
                                uint16_t current_ma)
{
    const uint32_t drop_mv = AbsDiffU16(open_mv, loaded_mv);
    uint32_t impedance = 0xFFFFU;
    if (current_ma != 0U)
    {
        impedance = (drop_mv * 1000U) / current_ma;
    }
    if (impedance > 0xFFFFU)
    {
        impedance = 0xFFFFU;
    }
    return (uint16_t)impedance;
}

static int16_t MedianOfThreeS16(int16_t first, int16_t second, int16_t third)
{
    int16_t temporary;
    if (first > second)
    {
        temporary = first;
        first = second;
        second = temporary;
    }
    if (second > third)
    {
        temporary = second;
        second = third;
        third = temporary;
    }
    if (first > second)
    {
        second = first;
    }
    return second;
}

static uint16_t MagnitudeS16(int16_t value)
{
    int32_t widened = value;
    if (widened < 0)
    {
        widened = -widened;
    }
    return (uint16_t)widened;
}

static uint16_t MixGatewayWord(uint16_t checksum, uint16_t value, uint8_t index)
{
    uint32_t mixed = checksum;
    mixed ^= (uint32_t)value << (index & 3U);
    mixed = (mixed << 3U) | (mixed >> 13U);
    mixed ^= 0x1021U + (uint32_t)index;
    return (uint16_t)mixed;
}

void AutomotiveHoldoutV6_Initialize(void)
{
    uint32_t index;
    uint32_t sensor;
    uint32_t sample;

    for (index = 0U; index < CELL_COUNT; ++index)
    {
        s_cell_voltage_mv[index] = (uint16_t)(4075U - index * 7U);
        s_cell_loaded_mv[index] = (uint16_t)(3990U - index * 9U);
        s_cell_current_ma[index] = (uint16_t)(1180U + index * 43U);
        s_cell_temperature[index] = (uint16_t)(42U + (index * 5U) % 31U);
    }
    for (sensor = 0U; sensor < STEERING_SENSOR_COUNT; ++sensor)
    {
        s_steering_limit[sensor] = (uint16_t)(34U + sensor * 3U);
        for (sample = 0U; sample < STEERING_SAMPLE_COUNT; ++sample)
        {
            s_steering_samples[sensor][sample] =
                (int16_t)((int32_t)(sensor * 11U + sample * 7U) - 18);
        }
    }
    for (index = 0U; index < GATEWAY_SIGNAL_COUNT; ++index)
    {
        s_gateway_alive[index] = (uint8_t)((index * 3U + 1U) & 0x0FU);
        s_gateway_previous_alive[index] =
            (uint8_t)((s_gateway_alive[index] - ((index == 5U) ? 0U : 1U)) &
                      0x0FU);
        s_gateway_age[index] = (uint8_t)(index + ((index == 5U) ? 9U : 1U));
        s_gateway_value[index] = (uint16_t)(700U + index * 61U);
    }
    s_gateway_state = 1U;
    s_holdout_v6_sink = 0U;
}

void BatteryImpedanceDerating_Task10ms(void)
{
    uint32_t cell;
    uint32_t impedance_sum = 0U;
    uint32_t derating_permille = 1000U;
    uint32_t weak_mask = 0U;
    uint16_t maximum_impedance = 0U;

    for (cell = 0U; cell < CELL_COUNT; ++cell)
    {
        const uint16_t impedance =
            CellImpedanceU16(s_cell_voltage_mv[cell],
                             s_cell_loaded_mv[cell],
                             s_cell_current_ma[cell]);
        impedance_sum += impedance;
        if (impedance > maximum_impedance)
        {
            maximum_impedance = impedance;
        }
        if ((impedance > 72U) || (s_cell_temperature[cell] > 65U))
        {
            weak_mask |= 1UL << cell;
            if (derating_permille >= 45U)
            {
                derating_permille -= 45U;
            }
        }
    }
    if (maximum_impedance > 90U)
    {
        derating_permille = (derating_permille * 7U) / 8U;
    }
    s_holdout_v6_sink = impedance_sum ^ derating_permille ^ weak_mask;
}

void SteeringSensorVoting_Task5ms(void)
{
    uint32_t sample;
    uint32_t disagreement_count = 0U;
    uint32_t checksum = 0U;
    int32_t voted_sum = 0;

    for (sample = 0U; sample < STEERING_SAMPLE_COUNT; ++sample)
    {
        const int16_t first = s_steering_samples[0U][sample];
        const int16_t second = s_steering_samples[1U][sample];
        const int16_t third = s_steering_samples[2U][sample];
        const int16_t voted = MedianOfThreeS16(first, second, third);
        const uint16_t delta_first =
            MagnitudeS16((int16_t)(first - voted));
        const uint16_t delta_second =
            MagnitudeS16((int16_t)(second - voted));
        const uint16_t delta_third =
            MagnitudeS16((int16_t)(third - voted));

        voted_sum += voted;
        if ((delta_first > s_steering_limit[0U]) ||
            (delta_second > s_steering_limit[1U]) ||
            (delta_third > s_steering_limit[2U]))
        {
            ++disagreement_count;
        }
        checksum = (checksum << 4U) ^ (uint16_t)voted ^ disagreement_count;
    }
    if (disagreement_count >= 2U)
    {
        voted_sum /= 2;
    }
    s_holdout_v6_sink = (uint32_t)voted_sum ^ checksum ^ disagreement_count;
}

void CanGatewayFreshness_Task10ms(void)
{
    uint32_t signal;
    uint32_t stale_mask = 0U;
    uint32_t changed_count = 0U;
    uint16_t checksum = 0xFFFFU;

    for (signal = 0U; signal < GATEWAY_SIGNAL_COUNT; ++signal)
    {
        const uint8_t alive = s_gateway_alive[signal];
        const uint8_t previous = s_gateway_previous_alive[signal];
        const uint8_t expected = (uint8_t)((previous + 1U) & 0x0FU);

        if (alive == expected)
        {
            s_gateway_age[signal] = 0U;
            ++changed_count;
        }
        else
        {
            uint8_t age = s_gateway_age[signal];
            if (age < 0xFFU)
            {
                ++age;
            }
            s_gateway_age[signal] = age;
            if (age > 8U)
            {
                stale_mask |= 1UL << signal;
            }
        }
        s_gateway_previous_alive[signal] = alive;
        checksum = MixGatewayWord(checksum, s_gateway_value[signal],
                                  (uint8_t)signal);
    }

    switch (s_gateway_state)
    {
        case 0U:
            if (changed_count >= 6U)
            {
                s_gateway_state = 1U;
            }
            break;
        case 1U:
            if (stale_mask != 0U)
            {
                s_gateway_state = 2U;
            }
            break;
        default:
            if ((stale_mask == 0U) && (changed_count == GATEWAY_SIGNAL_COUNT))
            {
                s_gateway_state = 1U;
            }
            break;
    }
    s_holdout_v6_sink = stale_mask ^ changed_count ^ checksum ^ s_gateway_state;
}
