#ifndef AUTOMOTIVE_BLIND_V8_TASKS_H
#define AUTOMOTIVE_BLIND_V8_TASKS_H

#include <stdint.h>

void BlindV8_Initialize(uint32_t task_id);
void RadarObjectAssociation_Task20ms(void);
void EgrAdaptiveControl_Task10ms(void);
void SecureCanFreshness_Task5ms(void);

#endif
