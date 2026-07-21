#define true 1
#define false 0

typedef unsigned char bool;
typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;
typedef int int32_t;

typedef struct
{
    uint16_t adc[8];
    uint32_t can_id;
    float value;
    float confidence;
    uint8_t state;
    uint8_t fault;
} StarAutomotiveSample;

extern uint16_t ADC_Read(uint8_t channel);
extern void ADC_Start(uint8_t channel);
extern void CAN_Send(uint32_t id, const void *payload, uint8_t length);
extern void GPIO_Write(uint32_t pin, bool value);
extern int xQueueSend(void *queue, const void *item, uint32_t timeout_ticks);
extern int xQueueReceive(void *queue, void *item, uint32_t timeout_ticks);
extern int xSemaphoreTake(void *semaphore, uint32_t timeout_ticks);
extern int xSemaphoreGive(void *semaphore);
extern void vTaskDelay(uint32_t ticks);

static volatile uint32_t g_star_benchmark_sink;

static uint32_t brake_sample_inputs(StarAutomotiveSample *sample)
{
    uint32_t checksum = 0U;

    for (uint8_t channel = 0U; channel < 8U; channel++)
    {
        ADC_Start(channel);
        sample->adc[channel] = ADC_Read(channel);
        checksum += sample->adc[channel] * (uint32_t)(channel + 1U);

        if (sample->adc[channel] > 3800U)
        {
            sample->fault++;
        }
        else if (sample->adc[channel] < 120U)
        {
            sample->fault += 2U;
        }
        else if ((sample->adc[channel] & 0x10U) != 0U)
        {
            sample->confidence += 0.25f;
        }
        else
        {
            sample->confidence += 0.10f;
        }
    }

    return checksum;
}

static float brake_estimate_slip(StarAutomotiveSample *sample, uint32_t checksum)
{
    float slip = 0.0f;

    for (uint8_t wheel = 0U; wheel < 4U; wheel++)
    {
        float front = (float)sample->adc[wheel];
        float rear = (float)sample->adc[wheel + 4U];
        float delta = front - rear;

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

        while (sample->adc[wheel] == 0U && sample->fault < 8U)
        {
            sample->fault++;
            sample->adc[wheel] = ADC_Read(wheel);
        }
    }

    if ((checksum & 0x03U) == 0U)
    {
        slip += 1.0f;
    }

    return slip;
}

static uint8_t brake_arbitrate_torque(StarAutomotiveSample *sample, float slip)
{
    uint8_t command = 0U;

    switch (sample->fault)
    {
    case 0U:
        command = (slip > 4.0f) ? 3U : 1U;
        break;
    case 1U:
    case 2U:
        command = (slip > 2.0f) ? 2U : 1U;
        break;
    default:
        command = 0U;
        break;
    }

    if (command == 3U)
    {
        GPIO_Write(10U, true);
        CAN_Send(0x180U, sample, sizeof(*sample));
    }
    else if (command == 2U)
    {
        GPIO_Write(10U, true);
        xQueueSend(0, sample, 0U);
    }
    else
    {
        GPIO_Write(10U, false);
    }

    return command;
}

void StarTask_5ms_BrakeControl(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t checksum = brake_sample_inputs(&sample);
    float slip = brake_estimate_slip(&sample, checksum);
    uint8_t command = brake_arbitrate_torque(&sample, slip);

    if (command == 0U && sample.fault > 3U)
    {
        xSemaphoreTake(context, 0U);
        GPIO_Write(11U, true);
        xSemaphoreGive(context);
    }
    else if (command > 1U)
    {
        CAN_Send(0x181U, &command, sizeof(command));
    }
    else
    {
        g_star_benchmark_sink += checksum;
    }
}

static uint32_t steering_collect_sensors(StarAutomotiveSample *sample)
{
    uint32_t effort = 0U;

    for (uint8_t index = 0U; index < 6U; index++)
    {
        sample->adc[index] = ADC_Read((uint8_t)(index + 8U));

        if (sample->adc[index] > 3000U)
        {
            effort += 9U;
        }
        else if (sample->adc[index] > 1600U)
        {
            effort += 5U;
        }
        else if (sample->adc[index] < 300U)
        {
            effort += 11U;
            sample->fault++;
        }
        else
        {
            effort += 2U;
        }
    }

    return effort;
}

static float steering_compute_assist(StarAutomotiveSample *sample, uint32_t effort)
{
    float assist = (float)effort * 0.125f;

    for (uint8_t step = 0U; step < 5U; step++)
    {
        if ((sample->adc[step] & 0x01U) != 0U)
        {
            assist += 0.75f;
        }
        else if ((sample->adc[step] & 0x02U) != 0U)
        {
            assist -= 0.25f;
        }
        else
        {
            assist += 0.10f;
        }

        switch ((sample->adc[step] >> 4U) & 0x03U)
        {
        case 0U:
            assist += 0.20f;
            break;
        case 1U:
            assist += 0.40f;
            break;
        case 2U:
            assist -= 0.30f;
            break;
        default:
            sample->fault++;
            break;
        }
    }

    return assist;
}

static void steering_publish_command(StarAutomotiveSample *sample, float assist)
{
    if (assist > 12.0f)
    {
        GPIO_Write(20U, true);
        CAN_Send(0x220U, sample, sizeof(*sample));
    }
    else if (assist < 1.0f)
    {
        GPIO_Write(20U, false);
        xQueueSend(0, sample, 0U);
    }
    else
    {
        CAN_Send(0x221U, &assist, sizeof(assist));
    }
}

void StarTask_10ms_SteeringAssist(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t effort = steering_collect_sensors(&sample);
    float assist = steering_compute_assist(&sample, effort);
    steering_publish_command(&sample, assist);

    if (sample.fault > 2U)
    {
        xSemaphoreTake(context, 0U);
        GPIO_Write(21U, true);
        xSemaphoreGive(context);
    }
}

static uint32_t crash_read_acceleration(StarAutomotiveSample *sample)
{
    uint32_t energy = 0U;

    for (uint8_t axis = 0U; axis < 6U; axis++)
    {
        sample->adc[axis] = ADC_Read((uint8_t)(axis + 16U));
        energy += sample->adc[axis] * sample->adc[axis];

        if (sample->adc[axis] > 3500U)
        {
            sample->fault += 3U;
        }
        else if (sample->adc[axis] > 2500U)
        {
            sample->fault += 1U;
        }
        else if (sample->adc[axis] < 100U)
        {
            sample->fault += 2U;
        }
        else
        {
            sample->confidence += 0.2f;
        }
    }

    return energy;
}

static uint8_t crash_classify_event(StarAutomotiveSample *sample, uint32_t energy)
{
    uint8_t severity = 0U;

    if (energy > 9000000U)
    {
        severity = 3U;
    }
    else if (energy > 5000000U)
    {
        severity = 2U;
    }
    else if (energy > 1000000U)
    {
        severity = 1U;
    }

    switch (sample->fault)
    {
    case 0U:
        break;
    case 1U:
    case 2U:
        severity++;
        break;
    default:
        severity = 3U;
        break;
    }

    return severity;
}

static void crash_publish_safety_state(StarAutomotiveSample *sample, uint8_t severity)
{
    if (severity >= 3U)
    {
        GPIO_Write(30U, true);
        CAN_Send(0x300U, sample, sizeof(*sample));
        xQueueSend(0, sample, 0U);
    }
    else if (severity == 2U)
    {
        CAN_Send(0x301U, &severity, sizeof(severity));
    }
    else
    {
        GPIO_Write(30U, false);
    }
}

void StarTask_25ms_CrashSafety(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t energy = crash_read_acceleration(&sample);

    if ((energy & 0x01U) != 0U)
    {
        energy += crash_read_acceleration(&sample) / 2U;
    }
    else
    {
        sample.confidence += 0.5f;
    }

    uint8_t severity = crash_classify_event(&sample, energy);

    if (severity > 1U)
    {
        severity += crash_classify_event(&sample, energy / 2U);
    }

    crash_publish_safety_state(&sample, severity);

    if (severity >= 3U)
    {
        xSemaphoreTake(context, 0U);
        crash_publish_safety_state(&sample, severity);
        xSemaphoreGive(context);
    }
}

static uint32_t thermal_sample_pack(StarAutomotiveSample *sample)
{
    uint32_t hot_cells = 0U;

    for (uint8_t cell = 0U; cell < 8U; cell++)
    {
        sample->adc[cell] = ADC_Read((uint8_t)(cell + 24U));

        if (sample->adc[cell] > 3300U)
        {
            hot_cells += 2U;
            sample->fault++;
        }
        else if (sample->adc[cell] > 2600U)
        {
            hot_cells++;
        }
        else if (sample->adc[cell] < 400U)
        {
            sample->fault += 2U;
        }
        else
        {
            sample->confidence += 0.1f;
        }
    }

    return hot_cells;
}

static float thermal_compute_derating(StarAutomotiveSample *sample, uint32_t hot_cells)
{
    float derating = (float)hot_cells * 0.05f;

    for (uint8_t cell = 0U; cell < 8U; cell++)
    {
        if ((sample->adc[cell] & 0x08U) != 0U)
        {
            derating += 0.02f;
        }
        else if ((sample->adc[cell] & 0x04U) != 0U)
        {
            derating += 0.01f;
        }

        if (derating > 0.7f)
        {
            break;
        }
    }

    return derating;
}

static void thermal_publish_derating(StarAutomotiveSample *sample, float derating)
{
    switch (sample->fault)
    {
    case 0U:
        CAN_Send(0x410U, &derating, sizeof(derating));
        break;
    case 1U:
    case 2U:
        xQueueSend(0, sample, 0U);
        break;
    default:
        GPIO_Write(40U, true);
        CAN_Send(0x411U, sample, sizeof(*sample));
        break;
    }
}

void StarTask_50ms_BatteryThermal(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t hot_cells = thermal_sample_pack(&sample);
    float derating = thermal_compute_derating(&sample, hot_cells);
    thermal_publish_derating(&sample, derating);

    if (derating > 0.5f)
    {
        xSemaphoreTake(context, 0U);
        xSemaphoreGive(context);
    }
}

static uint32_t powertrain_collect_torque(StarAutomotiveSample *sample)
{
    uint32_t torque = 0U;

    for (uint8_t sensor = 0U; sensor < 7U; sensor++)
    {
        sample->adc[sensor] = ADC_Read((uint8_t)(sensor + 32U));
        torque += sample->adc[sensor] / (uint32_t)(sensor + 1U);

        if (sample->adc[sensor] > 3600U)
        {
            sample->fault++;
        }
        else if (sample->adc[sensor] < 200U)
        {
            sample->fault += 2U;
        }
    }

    return torque;
}

static float powertrain_limit_request(StarAutomotiveSample *sample, uint32_t torque)
{
    float limit = (float)torque * 0.01f;

    if (limit > 100.0f)
    {
        limit = 100.0f;
    }
    else if (limit < 5.0f)
    {
        limit = 5.0f;
    }

    for (uint8_t gear = 0U; gear < 6U; gear++)
    {
        switch ((sample->adc[gear] >> 3U) & 0x03U)
        {
        case 0U:
            limit += 0.5f;
            break;
        case 1U:
            limit -= 0.25f;
            break;
        case 2U:
            limit += 1.0f;
            break;
        default:
            sample->fault++;
            break;
        }
    }

    return limit;
}

static void powertrain_publish_limit(StarAutomotiveSample *sample, float limit)
{
    if (sample->fault > 4U)
    {
        GPIO_Write(50U, true);
        xQueueSend(0, sample, 0U);
    }
    else if (limit > 80.0f)
    {
        CAN_Send(0x510U, &limit, sizeof(limit));
    }
    else
    {
        CAN_Send(0x511U, sample, sizeof(*sample));
    }
}

void StarTask_100ms_PowertrainManager(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t torque = powertrain_collect_torque(&sample);

    if ((torque & 0x04U) != 0U)
    {
        torque += powertrain_collect_torque(&sample) / 2U;
    }
    else if (torque > 12000U)
    {
        sample.fault++;
    }
    else
    {
        sample.confidence += 0.2f;
    }

    float limit = powertrain_limit_request(&sample, torque);

    if (sample.fault > 1U)
    {
        limit += powertrain_limit_request(&sample, torque / 2U);
    }

    powertrain_publish_limit(&sample, limit);

    if (sample.fault > 5U)
    {
        xSemaphoreTake(context, 0U);
        GPIO_Write(51U, true);
        powertrain_publish_limit(&sample, limit);
        xSemaphoreGive(context);
    }
}

static uint32_t diagnostic_collect_dtc(StarAutomotiveSample *sample)
{
    uint32_t dtc_mask = 0U;

    for (uint8_t module = 0U; module < 8U; module++)
    {
        sample->adc[module] = ADC_Read((uint8_t)(module + 40U));

        if (sample->adc[module] > 3400U)
        {
            dtc_mask |= (1UL << module);
        }
        else if (sample->adc[module] < 100U)
        {
            dtc_mask |= (1UL << (module + 8U));
        }
        else
        {
            sample->confidence += 0.05f;
        }
    }

    return dtc_mask;
}

static uint8_t diagnostic_rank_faults(StarAutomotiveSample *sample, uint32_t dtc_mask)
{
    uint8_t rank = 0U;

    for (uint8_t bit = 0U; bit < 16U; bit++)
    {
        if ((dtc_mask & (1UL << bit)) != 0U)
        {
            rank++;
        }
    }

    switch (rank)
    {
    case 0U:
        sample->state = 0U;
        break;
    case 1U:
    case 2U:
        sample->state = 1U;
        break;
    default:
        sample->state = 2U;
        break;
    }

    return rank;
}

static void diagnostic_publish_report(StarAutomotiveSample *sample, uint8_t rank)
{
    if (rank > 4U)
    {
        CAN_Send(0x620U, sample, sizeof(*sample));
        xQueueSend(0, sample, 0U);
    }
    else if (rank > 0U)
    {
        CAN_Send(0x621U, &rank, sizeof(rank));
    }
    else
    {
        GPIO_Write(60U, false);
    }
}

void StarTask_200ms_Diagnostics(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t dtc_mask = diagnostic_collect_dtc(&sample);
    uint8_t rank = diagnostic_rank_faults(&sample, dtc_mask);
    diagnostic_publish_report(&sample, rank);

    if (rank > 4U)
    {
        xQueueReceive(context, &sample, 0U);
    }
}

static uint32_t network_collect_frames(StarAutomotiveSample *sample)
{
    uint32_t score = 0U;

    for (uint8_t bus = 0U; bus < 6U; bus++)
    {
        sample->adc[bus] = ADC_Read((uint8_t)(bus + 48U));

        if (sample->adc[bus] > 3000U)
        {
            score += 8U;
        }
        else if (sample->adc[bus] > 1500U)
        {
            score += 3U;
        }
        else
        {
            score++;
        }
    }

    return score;
}

static uint8_t network_route_frames(StarAutomotiveSample *sample, uint32_t score)
{
    uint8_t route = 0U;

    if (score > 40U)
    {
        route = 3U;
    }
    else if (score > 20U)
    {
        route = 2U;
    }
    else
    {
        route = 1U;
    }

    switch (route)
    {
    case 1U:
        sample->can_id = 0x710U;
        break;
    case 2U:
        sample->can_id = 0x711U;
        break;
    default:
        sample->can_id = 0x712U;
        sample->fault++;
        break;
    }

    return route;
}

static void network_publish_gateway(StarAutomotiveSample *sample, uint8_t route)
{
    for (uint8_t frame = 0U; frame < 3U; frame++)
    {
        if (route == 3U)
        {
            CAN_Send(sample->can_id + frame, sample, sizeof(*sample));
        }
        else if (route == 2U)
        {
            xQueueSend(0, sample, 0U);
        }
        else
        {
            GPIO_Write(70U, false);
        }
    }
}

void StarTask_500ms_NetworkGateway(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t score = network_collect_frames(&sample);
    uint8_t route = network_route_frames(&sample, score);
    network_publish_gateway(&sample, route);

    if (sample.fault > 0U)
    {
        xSemaphoreTake(context, 0U);
        xSemaphoreGive(context);
    }
}

static uint32_t health_collect_lifetime_data(StarAutomotiveSample *sample)
{
    uint32_t aging = 0U;

    for (uint8_t index = 0U; index < 8U; index++)
    {
        sample->adc[index] = ADC_Read((uint8_t)(index + 56U));
        aging += sample->adc[index];

        if ((sample->adc[index] & 0x80U) != 0U)
        {
            sample->fault++;
        }
        else if ((sample->adc[index] & 0x40U) != 0U)
        {
            sample->confidence += 0.2f;
        }
    }

    return aging;
}

static float health_estimate_degradation(StarAutomotiveSample *sample, uint32_t aging)
{
    float degradation = (float)aging * 0.0001f;

    while (degradation > 1.0f && sample->fault < 10U)
    {
        degradation *= 0.75f;
        sample->fault++;
    }

    if (degradation > 0.8f)
    {
        sample->state = 3U;
    }
    else if (degradation > 0.5f)
    {
        sample->state = 2U;
    }
    else if (degradation > 0.2f)
    {
        sample->state = 1U;
    }
    else
    {
        sample->state = 0U;
    }

    return degradation;
}

static void health_publish_summary(StarAutomotiveSample *sample, float degradation)
{
    switch (sample->state)
    {
    case 0U:
        GPIO_Write(80U, false);
        break;
    case 1U:
        CAN_Send(0x810U, &degradation, sizeof(degradation));
        break;
    case 2U:
        CAN_Send(0x811U, sample, sizeof(*sample));
        break;
    default:
        GPIO_Write(80U, true);
        xQueueSend(0, sample, 0U);
        break;
    }
}

void StarTask_1000ms_VehicleHealth(void *context)
{
    StarAutomotiveSample sample = {0};
    uint32_t aging = health_collect_lifetime_data(&sample);

    if ((aging & 0x08U) != 0U)
    {
        aging += health_collect_lifetime_data(&sample);
    }
    else if (aging > 20000U)
    {
        aging += health_collect_lifetime_data(&sample) / 4U;
    }
    else
    {
        sample.confidence += 0.25f;
    }

    float degradation = health_estimate_degradation(&sample, aging);

    if (sample.fault > 2U)
    {
        degradation += health_estimate_degradation(&sample, aging / 2U);
    }

    health_publish_summary(&sample, degradation);

    if (degradation > 0.9f)
    {
        xQueueReceive(context, &sample, 0U);
        health_publish_summary(&sample, degradation);
    }
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
