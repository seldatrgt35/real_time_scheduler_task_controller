#ifndef BASIC_FEATURE_WCET_SUITE_H
#define BASIC_FEATURE_WCET_SUITE_H

typedef __UINT32_TYPE__ uint32_t;

void StarBasicSuite_Initialize(void);
void StarBasic_Arithmetic(void);
void StarBasic_DivideModulo(void);
void StarBasic_BitwiseShift(void);
void StarBasic_Branch(void);
void StarBasic_SequentialMemory(void);
void StarBasic_RandomMemory(void);
void StarBasic_MemoryCopy(void);
void StarBasic_MemorySet(void);
void StarBasic_FixedPoint(void);
void StarBasic_FloatingPoint(void);
void StarBasic_DirectCall(void);
void StarBasic_IndirectCall(void);
void StarBasic_Switch(void);

#endif
