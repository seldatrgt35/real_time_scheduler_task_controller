#ifndef AUTOMOTIVE_HOLDOUT_V2_H
#define AUTOMOTIVE_HOLDOUT_V2_H

void AutomotiveHoldoutV2_Initialize(void);
void AutomotiveHoldoutV2_ApplyScenario(
    __UINT32_TYPE__ task_id, __UINT32_TYPE__ scenario_id);
void BatteryContactorSupervisor_Task10ms(void);
void WheelSpeedFusion_Task5ms(void);
void DiagnosticEventAging_Task100ms(void);

#endif
