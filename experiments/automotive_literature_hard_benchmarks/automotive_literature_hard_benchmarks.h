#ifndef AUTOMOTIVE_LITERATURE_HARD_BENCHMARKS_H
#define AUTOMOTIVE_LITERATURE_HARD_BENCHMARKS_H

typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__  int32_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __INT16_TYPE__  int16_t;
typedef __UINT8_TYPE__  uint8_t;
typedef __INT8_TYPE__   int8_t;

void LiteratureHardBenchmarks_Initialize(uint32_t task_id);

void AdasKalmanFilter_Task10ms(void);
void CordicResolver_Task1ms(void);
void SecOcAesBlock_Task5ms(void);
void PowertrainKnockFft_Task20ms(void);
void AccAdaptiveControl_Task20ms(void);

#endif /* AUTOMOTIVE_LITERATURE_HARD_BENCHMARKS_H */
