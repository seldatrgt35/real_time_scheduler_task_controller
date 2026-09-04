#include "automotive_branch_v10_task.h"

#define PEDAL_SAMPLE_COUNT (12U)

static volatile uint16_t s_pedal_primary[PEDAL_SAMPLE_COUNT];
static volatile uint16_t s_pedal_secondary[PEDAL_SAMPLE_COUNT];
static volatile uint8_t s_fault_state;
static volatile uint8_t s_fault_counter;
static volatile uint8_t s_recovery_counter;
static volatile uint16_t s_validated_pedal;
static volatile uint32_t s_branch_v10_sink;

__attribute__((noinline))
static uint16_t DifferenceU16(uint16_t first, uint16_t second)
{
    uint16_t result;
    if (first >= second) { result = (uint16_t)(first - second); }
    else { result = (uint16_t)(second - first); }
    return result;
}

__attribute__((noinline))
static uint8_t ClassifyPedalPair(uint16_t primary, uint16_t secondary)
{
    uint8_t classification;
    const uint16_t difference = DifferenceU16(primary, secondary);
    if ((primary < 120U) || (primary > 3920U)) { classification = 3U; }
    else if ((secondary < 100U) || (secondary > 1980U)) { classification = 3U; }
    else if (difference > 420U) { classification = 2U; }
    else if (difference > 160U) { classification = 1U; }
    else { classification = 0U; }
    return classification;
}

void BranchV10_Initialize(void)
{
    uint32_t index;
    static const uint16_t primary_seed[PEDAL_SAMPLE_COUNT] = {
        820U, 910U, 1040U, 1180U, 1320U, 1490U,
        1660U, 1810U, 2050U, 2240U, 2470U, 2690U
    };
    static const uint16_t secondary_seed[PEDAL_SAMPLE_COUNT] = {
        410U, 452U, 535U, 580U, 705U, 730U,
        820U, 910U, 990U, 1130U, 1190U, 1360U
    };
    for (index = 0U; index < PEDAL_SAMPLE_COUNT; ++index)
    {
        s_pedal_primary[index] = primary_seed[index];
        s_pedal_secondary[index] = secondary_seed[index];
    }
    s_fault_state = 1U;
    s_fault_counter = 4U;
    s_recovery_counter = 1U;
    s_validated_pedal = 0U;
    s_branch_v10_sink = 0U;
}

void RedundantPedalFaultArbitration_Task5ms(void)
{
    uint32_t index;
    uint16_t accepted_sum = 0U;
    uint8_t warning_count = 0U;
    uint8_t severe_count = 0U;
    for (index = 0U; index < PEDAL_SAMPLE_COUNT; ++index)
    {
        const uint16_t primary = s_pedal_primary[index];
        const uint16_t secondary_scaled = (uint16_t)(s_pedal_secondary[index] << 1U);
        const uint8_t classification = ClassifyPedalPair(primary, secondary_scaled);
        if (classification == 0U) { accepted_sum = (uint16_t)(accepted_sum + primary); }
        else if (classification == 1U) { ++warning_count; }
        else { ++severe_count; }
    }
    if (severe_count >= 3U)
    {
        if (s_fault_counter < 15U) { ++s_fault_counter; }
        s_recovery_counter = 0U;
        if (s_fault_counter >= 6U) { s_fault_state = 2U; }
        else { s_fault_state = 1U; }
    }
    else if (warning_count >= 4U)
    {
        s_fault_state = 1U;
        if (s_fault_counter > 0U) { --s_fault_counter; }
        s_recovery_counter = 0U;
    }
    else
    {
        if (s_recovery_counter < 7U) { ++s_recovery_counter; }
        if (s_recovery_counter >= 3U)
        {
            s_fault_state = 0U;
            s_fault_counter = 0U;
        }
    }
    if (s_fault_state == 0U) { s_validated_pedal = (uint16_t)(accepted_sum / PEDAL_SAMPLE_COUNT); }
    else if (s_fault_state == 1U) { s_validated_pedal = (uint16_t)(accepted_sum >> 3U); }
    else { s_validated_pedal = 0U; }
    s_branch_v10_sink = ((uint32_t)s_fault_state << 24U) |
        ((uint32_t)severe_count << 16U) |
        ((uint32_t)warning_count << 8U) | s_validated_pedal;
}
