# LLM source-only WCET kör test promptu

Aşağıdaki görevi yalnızca verilen C kaynak kodundan analiz et. Kodun ELF,
assembly, map dosyası, kart ölçümü veya başka bir çalışma sonucu mevcut değil.
Herhangi bir araç çalıştırma, kodu derleme veya internetten benzer sonuç arama.

Hedef konfigürasyon:

- MCU: NXP S32K148, ARM Cortex-M4
- Core clock: 48 MHz
- Compiler: ARM GCC 11.4
- Optimization: `-O0`
- Floating-point kullanılmıyor
- Initialization fonksiyonu zaman ölçümünün dışında
- Ölçülen fonksiyon yalnızca `AutomotiveSensorMatrix_Task10ms`
- Tüm veriler internal SRAM'de
- Interrupt, DMA, scheduler/context-switch ve cache etkilerini dahil etme
- 10 ms değeri deadline'dır; çalışma süresi değildir

İstenen çalışma:

1. Dış ve iç döngü sınırlarını çıkar.
2. İç gövdenin toplam kaç kez çalıştığını hesapla.
3. Bellek okumaları, bellek yazmaları, integer toplama, shift, XOR, loop-control
   ve loop-setup işlerini ayrı ayrı açıkla.
4. Başlangıç fonksiyonunu tahmine dahil etme.
5. Bu hedef için source-only mühendislik tahmini üret:
   - `nominal_us`: en olası izole task süresi
   - `wcet_us`: belirsizliği kapsayan konservatif üst tahmin
6. WCET'in formal olarak kanıtlanmış olmadığını açıkça belirt.
7. Sonucu yalnızca aşağıdaki JSON şemasında ver; JSON dışında metin yazma.

```json
{
  "outer_iterations": 0,
  "inner_iterations_per_outer": 0,
  "total_inner_iterations": 0,
  "estimated_memory_reads": 0,
  "estimated_memory_writes": 0,
  "nominal_us": 0.0,
  "wcet_us": 0.0,
  "confidence_percent": 0,
  "assumptions": [""],
  "dominant_costs": [""]
}
```

Analiz edilecek kaynak kod:

```c
typedef unsigned int uint32_t;

#define SENSOR_COUNT  (8U)
#define SAMPLE_COUNT  (4U)

static uint32_t sensor_samples[SENSOR_COUNT][SAMPLE_COUNT];
static uint32_t filtered_sensor[SENSOR_COUNT];
static volatile uint32_t task_sink;

void AutomotiveSensorMatrix_Initialize(void)
{
    uint32_t sensor;
    uint32_t sample;
    for (sensor = 0U; sensor < SENSOR_COUNT; ++sensor)
    {
        for (sample = 0U; sample < SAMPLE_COUNT; ++sample)
        {
            sensor_samples[sensor][sample] =
                (sensor * 17U) + (sample * 5U) + 11U;
        }
        filtered_sensor[sensor] = 0U;
    }
    task_sink = 0U;
}

void AutomotiveSensorMatrix_Task10ms(void)
{
    uint32_t sensor;
    uint32_t sample;
    uint32_t checksum = 0U;
    for (sensor = 0U; sensor < SENSOR_COUNT; ++sensor)
    {
        uint32_t sum = 0U;
        for (sample = 0U; sample < SAMPLE_COUNT; ++sample)
        {
            sum += sensor_samples[sensor][sample];
        }
        filtered_sensor[sensor] = sum >> 2U;
        checksum ^= filtered_sensor[sensor];
    }
    task_sink = checksum;
}
```
