#ifndef SOURCE_ONLY_AUTOMOTIVE_TASKS_H
#define SOURCE_ONLY_AUTOMOTIVE_TASKS_H

typedef __UINT8_TYPE__ uint8_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT16_TYPE__ int16_t;
typedef __INT32_TYPE__ int32_t;

void SourceOnlyAutomotive_Initialize(void);
void SteeringPlausibility_Task5ms(void);
void BrakePressureVoting_Task10ms(void);
void InverterThermalDerating_Task20ms(void);

#endif
