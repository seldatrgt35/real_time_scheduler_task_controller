#ifndef DETERMINISTIC_AUTOMOTIVE_TASK_H
#define DETERMINISTIC_AUTOMOTIVE_TASK_H

typedef __UINT16_TYPE__ uint16_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;

typedef struct
{
    uint16_t pedal_raw[16];
    uint16_t speed_raw[16];
    uint16_t current_raw[16];
    uint32_t status_words[16];
} StarAutomotiveInputs;

typedef struct
{
    int32_t requested_torque_q15;
    uint32_t diagnostic_checksum;
    uint32_t packed_status;
    float thermal_derate;
} StarAutomotiveOutputs;

void StarAutomotiveTask_Initialize(void);
void StarAutomotiveTask_SensorAcquisition(void);
void StarAutomotiveTask_Plausibility(void);
void StarAutomotiveTask_Control(void);
void StarAutomotiveTask_Diagnostics(void);
void StarAutomotiveTask_OutputPacking(void);
void StarAutomotiveTask_10ms(void);
const StarAutomotiveOutputs *StarAutomotiveTask_GetOutputs(void);

#endif
