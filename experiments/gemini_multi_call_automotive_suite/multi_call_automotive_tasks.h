#ifndef MULTI_CALL_AUTOMOTIVE_TASKS_H
#define MULTI_CALL_AUTOMOTIVE_TASKS_H

void MultiCallAutomotive_Initialize(void);
void CoolingPumpDiagnostic_Task10ms(void);
void OccupantDoorSafety_Task20ms(void);
void CanSignalGateway_Task5ms(void);

#endif
