#ifndef AUTOMOTIVE_BLIND_V7_TASKS_H
#define AUTOMOTIVE_BLIND_V7_TASKS_H

#include <stdint.h>

void BlindV7_Initialize(uint32_t task_id);
void SensorVoting_Task10ms(void);
void NetworkDebounce_Task5ms(void);
void MotorThermalProtection_Task20ms(void);

#endif
