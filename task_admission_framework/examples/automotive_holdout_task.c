#include "automotive_holdout_task.h"
#if defined(__GNUC__) || defined(__clang__)
#define STAR_NOINLINE __attribute__((noinline))
#else
#define STAR_NOINLINE
#endif
typedef uint32_t(*transform_t)(uint32_t);
static uint32_t g_input[256],g_output[256];
static volatile uint32_t g_sink;
static STAR_NOINLINE uint32_t transform(uint32_t v){return v+19U;}
static const transform_t g_transform[2]={transform,transform};
void StarAutomotiveHoldout_Initialize(void){uint32_t i;for(i=0U;i<256U;++i){g_input[i]=i*11U+7U;g_output[i]=0U;}g_sink=0x2468ace1U;}
static STAR_NOINLINE void control_kernel(void){uint32_t i,v=g_sink|1U;for(i=0U;i<96U;++i){v+=i+5U;v*=((i&7U)+1U);v^=(i|0x33U);v=(v<<1U)|(v>>31U);if((i&1U)!=0U){v+=i;}else{v^=i;}}g_sink=v;}
static STAR_NOINLINE void memory_kernel(void){uint32_t i,v=g_sink;for(i=0U;i<128U;++i){v^=g_input[i];}for(i=0U;i<96U;++i){v+=g_input[(i*19U)&255U];}for(i=0U;i<48U;++i){g_output[i]=g_input[i];}for(i=48U;i<80U;++i){g_output[i]=0U;}g_sink=v;}
static STAR_NOINLINE void numeric_kernel(void){uint32_t i,q=g_sink|1U;float f=(float)(g_sink|1U);for(i=0U;i<64U;++i){q+=q*16U;}for(i=0U;i<24U;++i){f=f*0.875F;}g_sink=q^(uint32_t)f;}
static STAR_NOINLINE void communication_kernel(void){uint32_t i,v=g_sink;for(i=0U;i<64U;++i){v^=g_input[i]&255U;}for(i=0U;i<24U;++i){v=g_transform[i&1U](v);}for(i=0U;i<32U;++i){switch(i&3U){case 0U:v+=1U;break;case 1U:v^=2U;break;case 2U:v|=4U;break;default:v&=0xfffffffeU;break;}}g_sink=v;}
void StarTask_25ms_AutomotiveHoldout(void){control_kernel();memory_kernel();numeric_kernel();communication_kernel();}
