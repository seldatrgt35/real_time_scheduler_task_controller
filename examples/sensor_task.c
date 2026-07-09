#define pdMS_TO_TICKS(ms) (ms)
#define true 1
#define false 0

typedef unsigned char bool;
typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;

typedef struct
{
    float temperature;
    uint16_t adc_raw;
} SensorSample;

extern void GPIO_Write(uint32_t pin, bool value);
extern uint16_t ADC_Read(uint8_t channel);
extern void ADC_Start(uint8_t channel);
extern void CAN_Send(uint32_t id, const void *payload, uint8_t length);
extern int xQueueSend(void *queue, const void *item, uint32_t timeout_ticks);
extern void vTaskDelay(uint32_t ticks);
extern int printf(const char *format, ...);

static float convert_adc_to_temperature(uint16_t adc_raw)
{
    return ((float)adc_raw * 3.3f) / 4095.0f;
}

void SensorTask(void *parameters)
{
    SensorSample sample;
    uint8_t channel = 3U;

    ADC_Start(channel);

    for (uint8_t i = 0U; i < 10U; i++)
    {
        sample.adc_raw = ADC_Read(channel);
        sample.temperature = convert_adc_to_temperature(sample.adc_raw);

        if (sample.temperature > 80.0f)
        {
            GPIO_Write(5U, true);
        }
        else
        {
            GPIO_Write(5U, false);
        }

        while (sample.adc_raw == 0U)
        {
            sample.adc_raw = ADC_Read(channel);
        }

        switch (sample.adc_raw & 0x03U)
        {
        case 0U:
            CAN_Send(0x120U, &sample, sizeof(sample));
            break;
        default:
            xQueueSend(parameters, &sample, 0U);
            break;
        }

        printf("temperature=%f\n", sample.temperature);
        vTaskDelay(pdMS_TO_TICKS(10U));
    }
}
