#ifndef STAR_MISRA_AUTOMOTIVE_COMPLEX_TASK_H
#define STAR_MISRA_AUTOMOTIVE_COMPLEX_TASK_H

/* Compiler-provided exact-width types avoid a host-side standard-header dependency. */
typedef __UINT32_TYPE__ uint32_t;
typedef __INT32_TYPE__ int32_t;

/** Initialize deterministic task state. Call once before scheduler start. */
void StarMisraAutomotive_Initialize(void);

/** Execute the 5 ms integer and control-flow task. */
void StarTask_5ms_MisraControl(void);

/** Execute the 10 ms deterministic memory-processing task. */
void StarTask_10ms_MisraMemory(void);

/** Execute the 20 ms Q31 fixed-point control task. */
void StarTask_20ms_MisraFixedPoint(void);

/** Execute the 50 ms floating-point estimation task. */
void StarTask_50ms_MisraFloatingPoint(void);

/** Execute the 100 ms checksum and diagnostic task. */
void StarTask_100ms_MisraDiagnostics(void);

/** Execute every demo stage sequentially; not intended as a GUI task row. */
void StarTask_20ms_MisraAutomotiveComplex(void);

#endif /* STAR_MISRA_AUTOMOTIVE_COMPLEX_TASK_H */
