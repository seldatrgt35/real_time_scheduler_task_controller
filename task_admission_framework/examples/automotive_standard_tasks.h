#ifndef STAR_AUTOMOTIVE_STANDARD_TASKS_H
#define STAR_AUTOMOTIVE_STANDARD_TASKS_H

typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;

void StarAutomotive_Initialize(void);
void StarTask_5ms_SensorFusion(void);
void StarTask_10ms_SignalFilter(void);
void StarTask_20ms_MotorControl(void);
void StarTask_50ms_StateEstimator(void);
void StarTask_100ms_Diagnostics(void);

#endif
