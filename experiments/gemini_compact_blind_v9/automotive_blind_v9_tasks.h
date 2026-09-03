#ifndef AUTOMOTIVE_BLIND_V9_TASKS_H
#define AUTOMOTIVE_BLIND_V9_TASKS_H

#include <stdint.h>

void BlindV9_Initialize(uint32_t task_id);
void InjectorCylinderCorrection_Task5ms(void);
void BatteryContactorDiagnostic_Task10ms(void);
void TorqueVectoringAllocation_Task2ms(void);

#endif
