#include "automotive_blind_v8_tasks.h"

#define RADAR_TRACK_COUNT (4U)
#define RADAR_DETECTION_COUNT (5U)
#define EGR_SAMPLE_COUNT (8U)
#define SECURE_PAYLOAD_COUNT (12U)

typedef struct
{
    int16_t range;
    int16_t velocity;
} RadarPoint;

static volatile RadarPoint s_tracks[RADAR_TRACK_COUNT];
static volatile RadarPoint s_detections[RADAR_DETECTION_COUNT];
static volatile uint8_t s_track_assignment[RADAR_TRACK_COUNT];
static volatile int16_t s_egr_error_history[EGR_SAMPLE_COUNT];
static volatile int16_t s_egr_integrator;
static volatile int16_t s_egr_command;
static volatile uint8_t s_secure_payload[SECURE_PAYLOAD_COUNT];
static volatile uint8_t s_secure_expected_crc;
static volatile uint8_t s_secure_previous_counter;
static volatile uint8_t s_secure_failure_counter;
static volatile uint32_t s_blind_v8_sink;

__attribute__((noinline))
static uint16_t AbsoluteDifferenceS16(int16_t first, int16_t second)
{
    int32_t difference = (int32_t)first - (int32_t)second;
    if (difference < 0)
    {
        difference = -difference;
    }
    return (uint16_t)difference;
}

__attribute__((noinline))
static uint16_t RadarAssociationCost(
    int16_t track_range,
    int16_t track_velocity,
    int16_t detection_range,
    int16_t detection_velocity)
{
    const uint16_t range_error = AbsoluteDifferenceS16(
        track_range, detection_range);
    const uint16_t velocity_error = AbsoluteDifferenceS16(
        track_velocity, detection_velocity);
    return (uint16_t)(range_error + (velocity_error << 1U));
}

__attribute__((noinline))
static int16_t SaturateS16(int32_t value, int16_t lower, int16_t upper)
{
    int32_t result = value;
    if (result < (int32_t)lower)
    {
        result = lower;
    }
    else if (result > (int32_t)upper)
    {
        result = upper;
    }
    else
    {
        /* Value is already inside the permitted interval. */
    }
    return (int16_t)result;
}

__attribute__((noinline))
static int16_t SlewCommandS16(int16_t previous, int16_t requested)
{
    int16_t result = requested;
    if (requested > (int16_t)(previous + 24))
    {
        result = (int16_t)(previous + 24);
    }
    else if (requested < (int16_t)(previous - 24))
    {
        result = (int16_t)(previous - 24);
    }
    else
    {
        /* No slew correction is required. */
    }
    return result;
}

__attribute__((noinline))
static uint8_t ComputeCrc8(const volatile uint8_t *data, uint32_t length)
{
    uint32_t byte_index;
    uint8_t crc = 0xFFU;
    for (byte_index = 0U; byte_index < length; ++byte_index)
    {
        uint32_t bit_index;
        crc ^= data[byte_index];
        for (bit_index = 0U; bit_index < 8U; ++bit_index)
        {
            if ((crc & 0x80U) != 0U)
            {
                crc = (uint8_t)((crc << 1U) ^ 0x1DU);
            }
            else
            {
                crc = (uint8_t)(crc << 1U);
            }
        }
    }
    return crc;
}

void BlindV8_Initialize(uint32_t task_id)
{
    uint32_t index;
    static const RadarPoint track_seed[RADAR_TRACK_COUNT] = {
        {1200, -35}, {2650, 18}, {4100, -8}, {7350, 42}
    };
    static const RadarPoint detection_seed[RADAR_DETECTION_COUNT] = {
        {2690, 20}, {7420, 39}, {1175, -31}, {4055, -12}, {9000, 75}
    };
    static const int16_t egr_seed[EGR_SAMPLE_COUNT] = {
        35, -18, 42, -27, 16, 51, -33, 24
    };
    static const uint8_t payload_seed[SECURE_PAYLOAD_COUNT] = {
        0x34U, 0xA7U, 0x19U, 0xE2U, 0x5DU, 0x81U,
        0x0FU, 0xC3U, 0x76U, 0x48U, 0xB1U, 0x2AU
    };
    (void)task_id;
    for (index = 0U; index < RADAR_TRACK_COUNT; ++index)
    {
        s_tracks[index] = track_seed[index];
        s_track_assignment[index] = 0xFFU;
    }
    for (index = 0U; index < RADAR_DETECTION_COUNT; ++index)
    {
        s_detections[index] = detection_seed[index];
    }
    for (index = 0U; index < EGR_SAMPLE_COUNT; ++index)
    {
        s_egr_error_history[index] = egr_seed[index];
    }
    s_egr_integrator = 112;
    s_egr_command = 380;
    for (index = 0U; index < SECURE_PAYLOAD_COUNT; ++index)
    {
        s_secure_payload[index] = payload_seed[index];
    }
    s_secure_expected_crc = 0x4CU;
    s_secure_previous_counter = 0x33U;
    s_secure_failure_counter = 2U;
    s_blind_v8_sink = 0U;
}

void RadarObjectAssociation_Task20ms(void)
{
    uint32_t track;
    uint32_t checksum = 0U;
    for (track = 0U; track < RADAR_TRACK_COUNT; ++track)
    {
        uint32_t detection;
        uint16_t best_cost = 0xFFFFU;
        uint8_t best_index = 0xFFU;
        for (detection = 0U; detection < RADAR_DETECTION_COUNT; ++detection)
        {
            const uint16_t cost = RadarAssociationCost(
                s_tracks[track].range,
                s_tracks[track].velocity,
                s_detections[detection].range,
                s_detections[detection].velocity);
            if ((cost < best_cost) && (cost < 600U))
            {
                best_cost = cost;
                best_index = (uint8_t)detection;
            }
        }
        s_track_assignment[track] = best_index;
        checksum ^= ((uint32_t)best_index << (track * 4U)) | best_cost;
    }
    s_blind_v8_sink = checksum;
}

void EgrAdaptiveControl_Task10ms(void)
{
    uint32_t index;
    int32_t weighted_error = 0;
    for (index = 0U; index < EGR_SAMPLE_COUNT; ++index)
    {
        const int32_t weight = (int32_t)(index + 1U);
        weighted_error += (int32_t)s_egr_error_history[index] * weight;
    }
    s_egr_integrator = SaturateS16(
        (int32_t)s_egr_integrator + (weighted_error >> 4), -800, 800);
    {
        const int16_t requested = SaturateS16(
            420 + (weighted_error >> 2) + ((int32_t)s_egr_integrator >> 1),
            0,
            1000);
        s_egr_command = SlewCommandS16(s_egr_command, requested);
    }
    s_blind_v8_sink =
        ((uint32_t)(uint16_t)s_egr_command << 16U) |
        (uint32_t)(uint16_t)s_egr_integrator;
}

void SecureCanFreshness_Task5ms(void)
{
    const uint8_t calculated_crc = ComputeCrc8(
        s_secure_payload, SECURE_PAYLOAD_COUNT);
    const uint8_t received_counter = s_secure_payload[0];
    const uint8_t expected_counter = (uint8_t)(s_secure_previous_counter + 1U);
    uint32_t status = 0U;
    if ((calculated_crc == s_secure_expected_crc) &&
        (received_counter == expected_counter))
    {
        s_secure_failure_counter = 0U;
        s_secure_previous_counter = received_counter;
        status = 1U;
    }
    else
    {
        if (s_secure_failure_counter < 7U)
        {
            ++s_secure_failure_counter;
        }
        if (s_secure_failure_counter >= 3U)
        {
            status = 0x80000000UL | s_secure_failure_counter;
        }
        else
        {
            status = s_secure_failure_counter;
        }
    }
    s_blind_v8_sink = status ^ calculated_crc;
}
