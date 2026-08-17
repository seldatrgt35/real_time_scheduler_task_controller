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
void StarBasic_MaskedMultiply(void);
void StarBasic_MaskedDivide(void);
void StarBasic_MaskedModulo(void);
void StarBasic_BitwiseNested(void);
void StarBasic_Checksum(void);
void StarBasic_Q15Multiply(void);
void StarBasic_Q31Multiply(void);
void StarBasic_Q31Mac(void);
void StarBasic_Float32Add(void);
void StarBasic_Float32Divide(void);
void StarBasic_Float64Add(void);
void StarBasic_Float64Multiply(void);
void StarBasic_Float64Divide(void);
void StarBasic_IntToFloat(void);

#endif
