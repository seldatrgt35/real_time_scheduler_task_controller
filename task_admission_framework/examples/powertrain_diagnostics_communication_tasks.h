#ifndef STAR_POWERTRAIN_DIAGNOSTICS_COMMUNICATION_TASKS_H
#define STAR_POWERTRAIN_DIAGNOSTICS_COMMUNICATION_TASKS_H

void StarPowertrainCommunication_Initialize(void);
void PowertrainDiagnosticsTask_50ms(void);
void PowertrainCommunicationCpuTask_100ms(void);
void PowertrainCanTransmitTask_100ms(void);

#endif /* STAR_POWERTRAIN_DIAGNOSTICS_COMMUNICATION_TASKS_H */
