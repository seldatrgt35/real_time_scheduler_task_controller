#ifndef BASIC_MEMORY_CALIBRATION_H
#define BASIC_MEMORY_CALIBRATION_H

void StarMemory_Initialize(void);
void StarMemory_Sequential8(void);
void StarMemory_Sequential16(void);
void StarMemory_Sequential64(void);
void StarMemory_Random8(void);
void StarMemory_Random16(void);
void StarMemory_Random64(void);
void StarMemory_Copy8(void);
void StarMemory_Copy16(void);
void StarMemory_Copy64(void);
void StarMemory_Set8(void);
void StarMemory_Set16(void);
void StarMemory_Set64(void);

#endif
