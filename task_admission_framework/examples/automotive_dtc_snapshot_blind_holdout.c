/*
 * Blind automotive holdout: pack confirmed diagnostic trouble-code snapshots
 * into a bounded UDS response buffer. This source is validation-only and must
 * never be used to fit execution-time coefficients.
 */
#include "automotive_dtc_snapshot_blind_holdout.h"

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT32_TYPE__ uint32_t;

#define STAR_DTC_ENTRY_COUNT       (16U)
#define STAR_DTC_RESPONSE_SIZE     (64U)
#define STAR_DTC_CONFIRMED_MASK    (8U)
#define STAR_DTC_MIN_OCCURRENCES   (2U)
#define STAR_DTC_MAX_AGE           (40U)

typedef struct
{
    uint32_t code;
    uint8_t status;
    uint8_t occurrence_count;
    uint8_t age_cycles;
    uint8_t reserved;
} StarDtcSnapshot;

static StarDtcSnapshot s_dtc_entries[STAR_DTC_ENTRY_COUNT];
static uint8_t s_uds_response[STAR_DTC_RESPONSE_SIZE];
static volatile uint32_t s_snapshot_result;

void StarAutomotiveDtcSnapshot_Initialize(void)
{
    uint32_t index;

    for (index = 0U; index < STAR_DTC_ENTRY_COUNT; ++index)
    {
        s_dtc_entries[index].code = 0x010000UL + (index * 0x101UL);
        s_dtc_entries[index].status =
            (index & 1U) == 0U ? STAR_DTC_CONFIRMED_MASK : 0U;
        s_dtc_entries[index].occurrence_count = (uint8_t)((index % 4U) + 1U);
        s_dtc_entries[index].age_cycles = (uint8_t)(index * 3U);
        s_dtc_entries[index].reserved = 0U;
    }

    for (index = 0U; index < STAR_DTC_RESPONSE_SIZE; ++index)
    {
        s_uds_response[index] = 0U;
    }
    s_snapshot_result = 0U;
}

void StarTask_DtcSnapshotPack_20ms(void)
{
    uint32_t index;
    uint32_t destination = 0U;

    for (index = 0U; index < STAR_DTC_ENTRY_COUNT; ++index)
    {
        const StarDtcSnapshot * const entry = &s_dtc_entries[index];

        if (((entry->status & STAR_DTC_CONFIRMED_MASK) != 0U) &&
            (entry->occurrence_count >= STAR_DTC_MIN_OCCURRENCES) &&
            (entry->age_cycles <= STAR_DTC_MAX_AGE))
        {
            s_uds_response[destination] = (uint8_t)(entry->code >> 16U);
            s_uds_response[destination + 1U] =
                (uint8_t)(entry->code >> 8U);
            s_uds_response[destination + 2U] = (uint8_t)entry->code;
            s_uds_response[destination + 3U] = entry->status;
            destination += 4U;
        }
    }

    s_snapshot_result = destination ^ s_uds_response[0U];
}
