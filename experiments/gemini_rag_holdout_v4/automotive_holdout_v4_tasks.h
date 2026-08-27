#ifndef AUTOMOTIVE_HOLDOUT_V4_TASKS_H
#define AUTOMOTIVE_HOLDOUT_V4_TASKS_H

void AutomotiveHoldoutV4_Initialize(void);
void DcLinkRippleMonitor_Task1ms(void);
void NetworkSignalSupervision_Task10ms(void);
void InjectorPulseCompensation_Task5ms(void);

#endif
