#ifndef AUTOMOTIVE_HOLDOUT_V6_TASKS_H
#define AUTOMOTIVE_HOLDOUT_V6_TASKS_H

void AutomotiveHoldoutV6_Initialize(void);
void BatteryImpedanceDerating_Task10ms(void);
void SteeringSensorVoting_Task5ms(void);
void CanGatewayFreshness_Task10ms(void);

#endif
