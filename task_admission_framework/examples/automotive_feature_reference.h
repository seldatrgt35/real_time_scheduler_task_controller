#ifndef AUTOMOTIVE_FEATURE_REFERENCE_H
#define AUTOMOTIVE_FEATURE_REFERENCE_H

/* Scheduler entry points. Initialization is intentionally outside timed tasks. */
void AutomotiveFeatureReference_Initialize(void);
void AppTask_PowertrainInput_5ms(void);
void AppTask_SignalConditioning_10ms(void);
void AppTask_TorqueCoordination_20ms(void);
void AppTask_Diagnostics_50ms(void);
void AppTask_NetworkManagement_100ms(void);

#endif
