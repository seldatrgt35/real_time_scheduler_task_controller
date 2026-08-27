#ifndef AUTOMOTIVE_HOLDOUT_V3_TASKS_H
#define AUTOMOTIVE_HOLDOUT_V3_TASKS_H

void AutomotiveHoldoutV3_Initialize(void);
void BatteryBalancing_Task10ms(void);
void EpsTorqueArbitration_Task5ms(void);
void ThermalNetworkSupervision_Task20ms(void);

#endif
