#include "bms_supervision_task.h"

/*
 * Blind source-only automotive benchmark.
 * Inspired by common open-source BMS supervision responsibilities: cell
 * voltage/temperature monitoring, passive balancing and contactor control.
 * No source or measurement from this task is present in the RAG index.
 */

#define BMS_CELL_COUNT               (12U)
#define BMS_TASK_PERIOD_TICKS        (10U)
#define BMS_CELL_UV_MV               (2900U)
#define BMS_CELL_OV_MV               (4180U)
#define BMS_CELL_BALANCE_MV          (4050U)
#define BMS_CELL_DELTA_MV            (35U)
#define BMS_CELL_OT_DEGC_X10         (550U)
#define BMS_PRECHARGE_COMPLETE_PERMILLE (900U)

typedef enum
{
    BMS_CONTACTOR_OPEN = 0,
    BMS_CONTACTOR_PRECHARGE = 1,
    BMS_CONTACTOR_CLOSED = 2,
    BMS_CONTACTOR_FAULT = 3
} BmsContactorState;

typedef struct
{
    uint16_t cell_voltage_mv[BMS_CELL_COUNT];
    uint16_t cell_temperature_degc_x10[BMS_CELL_COUNT];
    uint16_t dc_link_voltage_mv;
    uint8_t enable_request;
} BmsInputs;

typedef struct
{
    uint32_t fault_bitmap;
    uint32_t balancing_mask;
    uint32_t status_checksum;
    uint16_t pack_voltage_mv;
    uint16_t minimum_cell_mv;
    uint16_t maximum_cell_mv;
    uint8_t contactor_state;
} BmsOutputs;

typedef void (*BmsTaskCallback)(void);

typedef struct
{
    BmsTaskCallback callback;
    uint32_t period_ticks;
    uint32_t next_release_tick;
} BmsScheduledTask;

static BmsInputs s_inputs;
static BmsOutputs s_outputs;
static uint16_t s_filtered_voltage_mv[BMS_CELL_COUNT];
static BmsContactorState s_contactor_state;
static volatile uint32_t s_bms_sink;

static uint32_t BmsRotateLeft32(uint32_t value, uint32_t shift)
{
    return (value << shift) | (value >> (32U - shift));
}

static uint16_t BmsFilterVoltage(uint16_t previous, uint16_t sample)
{
    const uint32_t accumulated = ((uint32_t)previous * 3U) + sample;
    return (uint16_t)(accumulated >> 2U);
}

static void BmsUpdateContactorState(uint32_t faults, uint16_t pack_voltage_mv)
{
    const uint32_t dc_link_scaled = (uint32_t)s_inputs.dc_link_voltage_mv * 1000U;
    const uint32_t precharge_limit =
        (uint32_t)pack_voltage_mv * BMS_PRECHARGE_COMPLETE_PERMILLE;

    switch (s_contactor_state)
    {
        case BMS_CONTACTOR_OPEN:
            if ((s_inputs.enable_request != 0U) && (faults == 0U))
            {
                s_contactor_state = BMS_CONTACTOR_PRECHARGE;
            }
            break;
        case BMS_CONTACTOR_PRECHARGE:
            if (faults != 0U)
            {
                s_contactor_state = BMS_CONTACTOR_FAULT;
            }
            else if (dc_link_scaled >= precharge_limit)
            {
                s_contactor_state = BMS_CONTACTOR_CLOSED;
            }
            else
            {
                /* Continue deterministic precharge monitoring. */
            }
            break;
        case BMS_CONTACTOR_CLOSED:
            if ((faults != 0U) || (s_inputs.enable_request == 0U))
            {
                s_contactor_state = BMS_CONTACTOR_OPEN;
            }
            break;
        default:
            if (s_inputs.enable_request == 0U)
            {
                s_contactor_state = BMS_CONTACTOR_OPEN;
            }
            break;
    }
}

static void BmsSupervision_Task10ms(void)
{
    uint32_t index;
    uint32_t pack_sum_mv = 0U;
    uint32_t faults = 0U;
    uint32_t balancing = 0U;
    uint32_t checksum = 0x6D2B79F5UL;
    uint16_t minimum_mv = 0xFFFFU;
    uint16_t maximum_mv = 0U;

    for (index = 0U; index < BMS_CELL_COUNT; ++index)
    {
        const uint16_t filtered = BmsFilterVoltage(
            s_filtered_voltage_mv[index], s_inputs.cell_voltage_mv[index]);
        const uint16_t temperature = s_inputs.cell_temperature_degc_x10[index];
        s_filtered_voltage_mv[index] = filtered;
        pack_sum_mv += filtered;

        if (filtered < minimum_mv)
        {
            minimum_mv = filtered;
        }
        if (filtered > maximum_mv)
        {
            maximum_mv = filtered;
        }
        if ((filtered < BMS_CELL_UV_MV) || (filtered > BMS_CELL_OV_MV))
        {
            faults |= 1UL << index;
        }
        if (temperature > BMS_CELL_OT_DEGC_X10)
        {
            faults |= 1UL << (index + 16U);
        }
        if ((filtered > BMS_CELL_BALANCE_MV) &&
            ((uint32_t)filtered > ((uint32_t)minimum_mv + BMS_CELL_DELTA_MV)))
        {
            balancing |= 1UL << index;
        }

        checksum ^= ((uint32_t)filtered << 16U) | temperature;
        checksum = BmsRotateLeft32(checksum, 5U) + index;
    }

    BmsUpdateContactorState(faults, (uint16_t)pack_sum_mv);
    s_outputs.fault_bitmap = faults;
    s_outputs.balancing_mask = balancing;
    s_outputs.status_checksum = checksum;
    s_outputs.pack_voltage_mv = (uint16_t)pack_sum_mv;
    s_outputs.minimum_cell_mv = minimum_mv;
    s_outputs.maximum_cell_mv = maximum_mv;
    s_outputs.contactor_state = (uint8_t)s_contactor_state;
    s_bms_sink = checksum ^ faults ^ balancing ^ pack_sum_mv;
}

static BmsScheduledTask s_scheduler_task =
{
    BmsSupervision_Task10ms,
    BMS_TASK_PERIOD_TICKS,
    BMS_TASK_PERIOD_TICKS
};

void BmsSupervision_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < BMS_CELL_COUNT; ++index)
    {
        s_inputs.cell_voltage_mv[index] = (uint16_t)(3980U + (index * 13U));
        s_inputs.cell_temperature_degc_x10[index] =
            (uint16_t)(310U + (index * 7U));
        s_filtered_voltage_mv[index] = s_inputs.cell_voltage_mv[index];
    }
    s_inputs.dc_link_voltage_mv = 43000U;
    s_inputs.enable_request = 1U;
    s_contactor_state = BMS_CONTACTOR_PRECHARGE;
    s_outputs.fault_bitmap = 0U;
    s_outputs.balancing_mask = 0U;
    s_outputs.status_checksum = 0U;
    s_bms_sink = 0U;
}

void BmsScheduler_PrepareRelease(uint32_t tick)
{
    s_scheduler_task.next_release_tick = tick;
}

void BmsScheduler_RunDueTask(uint32_t tick)
{
    if (tick >= s_scheduler_task.next_release_tick)
    {
        s_scheduler_task.next_release_tick += s_scheduler_task.period_ticks;
        s_scheduler_task.callback();
    }
}
