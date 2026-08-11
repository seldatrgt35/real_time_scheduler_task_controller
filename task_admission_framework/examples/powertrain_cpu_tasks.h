#ifndef STAR_POWERTRAIN_CPU_TASKS_H
#define STAR_POWERTRAIN_CPU_TASKS_H

void StarPowertrainCpu_Initialize(void);
void PowertrainFastControlTask_5ms(void);
void PowertrainSensorTask_10ms(void);
void PowertrainTorqueSafetyTask_20ms(void);

#endif /* STAR_POWERTRAIN_CPU_TASKS_H */
