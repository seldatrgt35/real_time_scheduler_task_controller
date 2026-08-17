#ifndef ISO14229_REAL_AUTOMOTIVE_BLIND_SUITE_H
#define ISO14229_REAL_AUTOMOTIVE_BLIND_SUITE_H

void StarIso14229RealSuite_Initialize(void);
void StarTask_UdsReadDidPack_10ms(void);
void StarTask_UdsAddressLengthDecode_20ms(void);
void StarTask_UdsTransferDataBlock_5ms(void);
void StarTask_UdsSecurityKeyValidate_20ms(void);

#endif
