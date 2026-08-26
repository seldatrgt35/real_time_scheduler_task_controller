#ifndef AUTOMOTIVE_HOLDOUT_V2_H
#define AUTOMOTIVE_HOLDOUT_V2_H

void AutomotiveHoldoutV2_Initialize(void);
void AutomotiveHoldoutV2_ApplyScenario(unsigned int task_id, unsigned int scenario_id);
void BatteryContactorSupervisor_Task10ms(void);
void WheelSpeedFusion_Task5ms(void);
void DiagnosticEventAging_Task100ms(void);

#endif
