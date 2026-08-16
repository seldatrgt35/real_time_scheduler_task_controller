#ifndef BODY_CHASSIS_CONTROL_HOLDOUT_H
#define BODY_CHASSIS_CONTROL_HOLDOUT_H

void BodyChassisControl_Initialize(void);
void BccTask_WheelSpeedAndBrake_5ms(void);
void BccTask_ThermalActuator_10ms(void);
void BccTask_StabilityRequest_20ms(void);
void BccTask_FaultManager_50ms(void);
void BccTask_StatusCommunication_100ms(void);

#endif
