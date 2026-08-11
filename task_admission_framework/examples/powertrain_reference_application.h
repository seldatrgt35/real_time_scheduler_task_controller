#ifndef STAR_POWERTRAIN_REFERENCE_APPLICATION_H
#define STAR_POWERTRAIN_REFERENCE_APPLICATION_H

void StarPowertrainReference_Initialize(void);
void StarTask_PowertrainFastControl_5ms(void);
void StarTask_PowertrainSensorProcessing_10ms(void);
void StarTask_PowertrainTorqueSafety_20ms(void);
void StarTask_PowertrainDiagnostics_50ms(void);
void StarTask_PowertrainCommunication_100ms(void);
void StarTask_PowertrainCommunicationWithCan_100ms(void);

#endif /* STAR_POWERTRAIN_REFERENCE_APPLICATION_H */
