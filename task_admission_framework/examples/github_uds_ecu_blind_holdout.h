#ifndef STAR_GITHUB_UDS_ECU_BLIND_HOLDOUT_H
#define STAR_GITHUB_UDS_ECU_BLIND_HOLDOUT_H

void StarGithubUds_Initialize(void);
void StarTask_UdsCanRxDispatch_5ms(void);
void StarTask_ObdPidDecode_10ms(void);
void StarTask_UdsResponseValidation_20ms(void);
void StarTask_DtcAndSessionMaintenance_50ms(void);
void StarTask_ObdRequestAndCanTx_100ms(void);
void StarTask_UdsRequestMatchSupported_5ms(void);
void StarTask_UdsPayloadPackSupported_10ms(void);
void StarTask_UdsChecksumSupported_20ms(void);

#endif
