#define true 1
#define false 0

typedef unsigned char bool;
typedef unsigned char uint8_t;
typedef unsigned int uint32_t;
typedef unsigned short uint16_t;
typedef unsigned int star_size_t;

typedef struct
{
    uint16_t adc[8];
    uint32_t can_id;
    float value;
    float confidence;
    uint8_t state;
    uint8_t fault;
} StarAutomotiveSample;

extern uint32_t rts_s32k148_cycle_now(void);
extern void rts_s32k148_red_led_set(bool enabled);

static volatile uint32_t g_star_benchmark_sink;

static uint16_t star_adc_read(uint8_t channel)
{
    uint32_t seed = rts_s32k148_cycle_now() ^ ((uint32_t)channel * 7919U);
    return (uint16_t)((seed ^ (seed >> 7U)) & 0x0FFFU);
}

static void star_can_publish(uint32_t id, const void *payload, star_size_t length)
{
    const uint8_t *bytes = (const uint8_t *)payload;
    star_size_t index;

    g_star_benchmark_sink ^= id + (uint32_t)length;
    for (index = 0U; index < length; ++index)
    {
        g_star_benchmark_sink = (g_star_benchmark_sink << 3U) ^ bytes[index];
    }
}

static uint32_t star_sensor_window(
    StarAutomotiveSample *sample,
    uint8_t base_channel,
    uint8_t limit
)
{
    uint32_t score = 0U;
    uint8_t index;

    for (index = 0U; index < limit; ++index)
    {
        uint16_t raw = star_adc_read((uint8_t)(base_channel + index));
        sample->adc[index & 0x07U] = raw;
        score += raw * (uint32_t)(index + 1U);

        if (raw > 3600U)
        {
            sample->fault += 2U;
        }
        else if (raw > 2400U)
        {
            sample->confidence += 0.20f;
        }
        else if (raw < 200U)
        {
            sample->fault++;
        }
        else
        {
            sample->confidence += 0.05f;
        }
    }

    return score;
}

static float star_state_machine_score(
    StarAutomotiveSample *sample,
    uint32_t score
)
{
    float value = (float)(score & 0x0FFFU) * 0.001f;
    uint8_t step;

    for (step = 0U; step < 4U; ++step)
    {
        switch ((score >> (step * 2U)) & 0x03U)
        {
        case 0U:
            value += 0.20f;
            break;
        case 1U:
            value += 0.75f;
            sample->state = 1U;
            break;
        case 2U:
            value -= 0.35f;
            sample->state = 2U;
            break;
        default:
            value += 1.10f;
            sample->fault++;
            sample->state = 3U;
            break;
        }
    }

    if (value > 5.0f)
    {
        rts_s32k148_red_led_set(true);
    }
    else if (sample->fault > 2U)
    {
        rts_s32k148_red_led_set(false);
    }

    return value;
}

static void star_publish_state(
    StarAutomotiveSample *sample,
    uint32_t base_id,
    uint8_t repetitions
)
{
    uint8_t index;

    for (index = 0U; index < repetitions; ++index)
    {
        if (sample->state >= 3U)
        {
            star_can_publish(base_id + index, sample, sizeof(*sample));
        }
        else if (sample->fault > index)
        {
            star_can_publish(base_id + 0x10U + index, &sample->fault, sizeof(sample->fault));
        }
        else
        {
            g_star_benchmark_sink += base_id + index + sample->state;
        }
    }
}

static uint32_t brake_sample_inputs(StarAutomotiveSample *sample)
{
    uint32_t checksum = 0U;
    uint8_t channel;

    for (channel = 0U; channel < 8U; ++channel)
    {
        sample->adc[channel] = star_adc_read(channel);
        checksum += sample->adc[channel] * (uint32_t)(channel + 1U);
        if (sample->adc[channel] > 3800U)
        {
            sample->fault++;
        }
        else if (sample->adc[channel] < 120U)
        {
            sample->fault += 2U;
        }
        else
        {
            sample->confidence +=
                ((sample->adc[channel] & 0x10U) != 0U) ? 0.25f : 0.10f;
        }
    }
    return checksum;
}

static float brake_estimate_slip(StarAutomotiveSample *sample, uint32_t checksum)
{
    float slip = 0.0f;
    uint8_t wheel;

    for (wheel = 0U; wheel < 4U; ++wheel)
    {
        float delta = (float)sample->adc[wheel] -
                      (float)sample->adc[wheel + 4U];
        if (delta > 900.0f)
        {
            slip += 3.5f;
        }
        else if (delta > 450.0f)
        {
            slip += 2.0f;
        }
        else if (delta < -450.0f)
        {
            slip -= 1.5f;
        }
        else
        {
            slip += delta * 0.001f;
        }
    }
    return slip + (((checksum & 3U) == 0U) ? 1.0f : 0.0f);
}

static void StarTask_5ms_BrakeControl(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t checksum = brake_sample_inputs(&sample);
    float slip = brake_estimate_slip(&sample, checksum);
    uint8_t command = (sample.fault > 3U) ? 0U : ((slip > 4.0f) ? 3U : 1U);

    (void)context;
    rts_s32k148_red_led_set(command == 3U);
    if (command > 1U)
    {
        star_can_publish(0x180U, &sample, sizeof(sample));
    }
    else
    {
        g_star_benchmark_sink += checksum;
    }
}

static void StarTask_10ms_SteeringAssist(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t effort = 0U;
    uint8_t index;

    (void)context;
    for (index = 0U; index < 6U; ++index)
    {
        sample.adc[index] = star_adc_read((uint8_t)(index + 8U));
        effort += (sample.adc[index] > 3000U)
                      ? 9U
                      : ((sample.adc[index] < 300U) ? 11U : 3U);
    }
    sample.value = (float)effort * 0.125f;
    sample.value += star_state_machine_score(&sample, effort);
    rts_s32k148_red_led_set(sample.value > 12.0f);
    star_can_publish(0x220U, &sample.value, sizeof(sample.value));
}

static void StarTask_25ms_CrashSafety(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t energy = 0U;
    uint8_t axis;

    (void)context;
    for (axis = 0U; axis < 6U; ++axis)
    {
        sample.adc[axis] = star_adc_read((uint8_t)(axis + 16U));
        energy += (uint32_t)sample.adc[axis] * sample.adc[axis];
        if (sample.adc[axis] > 3500U)
        {
            sample.fault += 3U;
        }
    }
    sample.state = (energy > 9000000U || sample.fault > 2U) ? 3U : 0U;
    energy += star_sensor_window(&sample, 64U, 4U);
    energy += star_sensor_window(&sample, 68U, 6U);
    sample.value = star_state_machine_score(&sample, energy);
    sample.value += star_state_machine_score(&sample, energy >> 1U);
    rts_s32k148_red_led_set(sample.state >= 3U);
    if (sample.state >= 3U)
    {
        star_can_publish(0x300U, &sample, sizeof(sample));
    }
    star_publish_state(&sample, 0x301U, 2U);
}

static void StarTask_50ms_BatteryThermal(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t hot_cells = 0U;
    uint8_t cell;

    (void)context;
    for (cell = 0U; cell < 8U; ++cell)
    {
        sample.adc[cell] = star_adc_read((uint8_t)(cell + 24U));
        if (sample.adc[cell] > 3300U)
        {
            hot_cells += 2U;
            sample.fault++;
        }
        else if (sample.adc[cell] > 2600U)
        {
            hot_cells++;
        }
    }
    hot_cells += star_sensor_window(&sample, 72U, 6U);
    hot_cells += star_sensor_window(&sample, 80U, 3U);
    hot_cells += star_sensor_window(&sample, 84U, 8U);
    sample.value = (float)hot_cells * 0.05f;
    sample.value += star_state_machine_score(&sample, hot_cells);
    sample.value += star_state_machine_score(&sample, hot_cells >> 1U);
    star_can_publish(0x410U, &sample.value, sizeof(sample.value));
    star_publish_state(&sample, 0x411U, 3U);
}

static void StarTask_100ms_PowertrainManager(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t torque = 0U;
    uint8_t sensor;

    (void)context;
    for (sensor = 0U; sensor < 7U; ++sensor)
    {
        sample.adc[sensor] = star_adc_read((uint8_t)(sensor + 32U));
        torque += sample.adc[sensor] / (uint32_t)(sensor + 1U);
        if (sample.adc[sensor] > 3600U)
        {
            sample.fault++;
        }
    }
    torque += star_sensor_window(&sample, 88U, 6U);
    torque += star_sensor_window(&sample, 96U, 6U);
    torque += star_sensor_window(&sample, 100U, 8U);
    sample.value = (float)torque * 0.01f;
    sample.value += star_state_machine_score(&sample, torque);
    sample.value += star_state_machine_score(&sample, torque >> 1U);
    sample.value += star_state_machine_score(&sample, torque >> 2U);
    star_can_publish(0x510U, &sample.value, sizeof(sample.value));
    star_publish_state(&sample, 0x511U, 4U);
}

static void StarTask_200ms_Diagnostics(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t dtc_mask = 0U;
    uint8_t module;

    (void)context;
    for (module = 0U; module < 8U; ++module)
    {
        sample.adc[module] = star_adc_read((uint8_t)(module + 40U));
        if (sample.adc[module] > 3400U || sample.adc[module] < 100U)
        {
            dtc_mask |= 1UL << module;
        }
    }
    dtc_mask ^= star_sensor_window(&sample, 104U, 5U);
    dtc_mask ^= star_sensor_window(&sample, 108U, 7U);
    sample.state = (dtc_mask == 0U) ? 0U : 1U;
    sample.value = star_state_machine_score(&sample, dtc_mask);
    sample.value += star_state_machine_score(&sample, dtc_mask >> 1U);
    star_can_publish(0x620U, &dtc_mask, sizeof(dtc_mask));
    star_publish_state(&sample, 0x621U, 2U);
}

static void StarTask_500ms_NetworkGateway(void *context)
{
    StarAutomotiveSample sample = {0};
    uint8_t bus;
    uint32_t score = 0U;

    (void)context;
    for (bus = 0U; bus < 6U; ++bus)
    {
        score += star_adc_read((uint8_t)(bus + 48U)) > 1500U ? 3U : 1U;
    }
    score += star_sensor_window(&sample, 112U, 2U);
    sample.can_id = (score > 12U) ? 0x712U : 0x710U;
    star_can_publish(sample.can_id, &score, sizeof(score));
}

static void StarTask_1000ms_VehicleHealth(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t aging = 0U;
    uint8_t index;

    (void)context;
    for (index = 0U; index < 8U; ++index)
    {
        aging += star_adc_read((uint8_t)(index + 56U));
    }
    aging += star_sensor_window(&sample, 120U, 8U);
    aging += star_sensor_window(&sample, 128U, 8U);
    aging += star_sensor_window(&sample, 136U, 4U);
    aging += star_sensor_window(&sample, 140U, 8U);
    aging += star_sensor_window(&sample, 148U, 6U);
    sample.value = (float)aging * 0.0001f;
    sample.value += star_state_machine_score(&sample, aging);
    sample.value += star_state_machine_score(&sample, aging >> 1U);
    sample.value += star_state_machine_score(&sample, aging >> 2U);
    sample.state = (sample.value > 0.8f)
                       ? 3U
                       : ((sample.value > 0.5f) ? 2U : 0U);
    star_can_publish(0x810U, &sample.value, sizeof(sample.value));
    star_publish_state(&sample, 0x811U, 5U);
}

void Star_RunAllAutomotiveBenchmarksOnce(void *context)
{
    StarTask_5ms_BrakeControl(context);
    StarTask_10ms_SteeringAssist(context);
    StarTask_25ms_CrashSafety(context);
    StarTask_50ms_BatteryThermal(context);
    StarTask_100ms_PowertrainManager(context);
    StarTask_200ms_Diagnostics(context);
    StarTask_500ms_NetworkGateway(context);
    StarTask_1000ms_VehicleHealth(context);
}

int main(void)
{
    Star_RunAllAutomotiveBenchmarksOnce(0);
    return (int)g_star_benchmark_sink;
}
