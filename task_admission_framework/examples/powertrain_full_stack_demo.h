#ifndef STAR_POWERTRAIN_FULL_STACK_DEMO_H
#define STAR_POWERTRAIN_FULL_STACK_DEMO_H

void StarPowertrainDemo_Initialize(void);
void StarIsr_AdcComplete(void);
void StarTask_PedalAndTorqueControl_5ms(void);
void StarTask_SensorFusionAndSpeed_10ms(void);
void StarTask_TorqueLimiterAndTraction_20ms(void);
void StarTask_DiagnosticsAndPlausibility_50ms(void);
void StarTask_CanObdAndNetworkManagement_100ms(void);

#endif /* STAR_POWERTRAIN_FULL_STACK_DEMO_H */
