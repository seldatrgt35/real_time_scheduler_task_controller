#include "automotive_literature_hard_benchmarks.h"

volatile uint32_t g_bench_sink32;
volatile uint8_t  g_bench_sink8;

/* ========================================================================= */
/* 1. ADAS KALMAN FILTER (2D State: [Position, Velocity])                    */
/* ========================================================================= */
#define KF_SCALE 256

static int32_t s_kf_x[2];        /* [pos, vel] */
static int32_t s_kf_P[2][2];     /* Error covariance */
static int32_t s_kf_A[2][2];     /* State transition */
static int32_t s_kf_Q[2][2];     /* Process noise */
static int32_t s_kf_meas_pos;    /* Input measurement */

static void MatrixMult2x2(const int32_t A[2][2], const int32_t B[2][2], int32_t Out[2][2])
{
    uint32_t i, j, k;
    for (i = 0U; i < 2U; ++i)
    {
        for (j = 0U; j < 2U; ++j)
        {
            int32_t sum = 0;
            for (k = 0U; k < 2U; ++k)
            {
                sum += (A[i][k] * B[k][j]) / KF_SCALE;
            }
            Out[i][j] = sum;
        }
    }
}

static void MatrixAdd2x2(const int32_t A[2][2], const int32_t B[2][2], int32_t Out[2][2])
{
    uint32_t i, j;
    for (i = 0U; i < 2U; ++i)
    {
        for (j = 0U; j < 2U; ++j)
        {
            Out[i][j] = A[i][j] + B[i][j];
        }
    }
}

static void KalmanPredict(void)
{
    int32_t temp_P[2][2];
    int32_t AT[2][2];
    int32_t AP[2][2];

    /* x = A * x */
    int32_t new_x0 = (s_kf_A[0][0] * s_kf_x[0] + s_kf_A[0][1] * s_kf_x[1]) / KF_SCALE;
    int32_t new_x1 = (s_kf_A[1][0] * s_kf_x[0] + s_kf_A[1][1] * s_kf_x[1]) / KF_SCALE;
    s_kf_x[0] = new_x0;
    s_kf_x[1] = new_x1;

    /* AT = transpose(A) */
    AT[0][0] = s_kf_A[0][0]; AT[0][1] = s_kf_A[1][0];
    AT[1][0] = s_kf_A[0][1]; AT[1][1] = s_kf_A[1][1];

    /* P = A * P * AT + Q */
    MatrixMult2x2(s_kf_A, s_kf_P, AP);
    MatrixMult2x2(AP, AT, temp_P);
    MatrixAdd2x2(temp_P, s_kf_Q, s_kf_P);
}

static void KalmanUpdate(int32_t z_pos)
{
    /* H = [1, 0], R = 32 */
    /* Innovation: y = z - H*x */
    int32_t y = z_pos - s_kf_x[0];
    /* S = H * P * H^T + R = P[0][0] + R */
    int32_t S = s_kf_P[0][0] + 32;
    if (S <= 0) { S = 1; }

    /* Kalman Gain: K = P * H^T / S -> K[0] = P[0][0]/S, K[1] = P[1][0]/S */
    int32_t K0 = (s_kf_P[0][0] * KF_SCALE) / S;
    int32_t K1 = (s_kf_P[1][0] * KF_SCALE) / S;

    /* x = x + K * y */
    s_kf_x[0] += (K0 * y) / KF_SCALE;
    s_kf_x[1] += (K1 * y) / KF_SCALE;

    /* P = (I - K*H) * P */
    int32_t I_KH[2][2];
    int32_t new_P[2][2];
    I_KH[0][0] = KF_SCALE - K0;
    I_KH[0][1] = 0;
    I_KH[1][0] = -K1;
    I_KH[1][1] = KF_SCALE;

    MatrixMult2x2(I_KH, s_kf_P, new_P);
    s_kf_P[0][0] = new_P[0][0];
    s_kf_P[0][1] = new_P[0][1];
    s_kf_P[1][0] = new_P[1][0];
    s_kf_P[1][1] = new_P[1][1];
}

void AdasKalmanFilter_Task10ms(void)
{
    KalmanPredict();
    KalmanUpdate(s_kf_meas_pos);
    g_bench_sink32 = (uint32_t)(s_kf_x[0] + s_kf_x[1]);
}

/* ========================================================================= */
/* 2. CORDIC RESOLVER (16-iteration PMSM Rotor Angle Vectoring/Rotation)      */
/* ========================================================================= */
#define CORDIC_STAGES 16U

static const int32_t s_cordic_atan_lut[16] = {
    11520, 6800, 3593, 1824, 916, 458, 229, 115,
       57,   29,   14,    7,   4,   2,   1,   0
};

static int32_t s_cordic_target_angle;

static void CordicStep(int32_t *x, int32_t *y, int32_t *z, uint32_t i, int32_t atan_val)
{
    int32_t x_curr = *x;
    int32_t y_curr = *y;
    int32_t z_curr = *z;
    int32_t x_shift = x_curr >> i;
    int32_t y_shift = y_curr >> i;

    if (z_curr >= 0)
    {
        *x = x_curr - y_shift;
        *y = y_curr + x_shift;
        *z = z_curr - atan_val;
    }
    else
    {
        *x = x_curr + y_shift;
        *y = y_curr - x_shift;
        *z = z_curr + atan_val;
    }
}

static void CordicVectorRotate(int32_t angle, int32_t *cos_out, int32_t *sin_out)
{
    int32_t x = 9949; /* 0.607252935 * 16384 (CORDIC gain K * 2^14) */
    int32_t y = 0;
    int32_t z = angle;
    uint32_t i;

    for (i = 0U; i < CORDIC_STAGES; ++i)
    {
        CordicStep(&x, &y, &z, i, s_cordic_atan_lut[i]);
    }

    *cos_out = x;
    *sin_out = y;
}

void CordicResolver_Task1ms(void)
{
    int32_t cos_val = 0;
    int32_t sin_val = 0;
    CordicVectorRotate(s_cordic_target_angle, &cos_val, &sin_val);
    g_bench_sink32 = (uint32_t)(cos_val ^ (sin_val << 16));
}

/* ========================================================================= */
/* 3. SECOC AES-128 SINGLE BLOCK (10 Rounds, AUTOSAR SecOC)                  */
/* ========================================================================= */
static const uint8_t s_aes_sbox[256] = {
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5e, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16
};

static uint8_t s_aes_state[16];
static const uint8_t s_aes_round_key[16] = {
    0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
    0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c
};

static void AesSubBytes(uint8_t state[16])
{
    uint32_t i;
    for (i = 0U; i < 16U; ++i)
    {
        state[i] = s_aes_sbox[state[i]];
    }
}

static void AesShiftRows(uint8_t state[16])
{
    uint8_t temp;
    /* Row 1: shift left by 1 */
    temp = state[1];
    state[1] = state[5];
    state[5] = state[9];
    state[9] = state[13];
    state[13] = temp;

    /* Row 2: shift left by 2 */
    temp = state[2];
    state[2] = state[10];
    state[10] = temp;
    temp = state[6];
    state[6] = state[14];
    state[14] = temp;

    /* Row 3: shift left by 3 */
    temp = state[15];
    state[15] = state[11];
    state[11] = state[7];
    state[7] = state[3];
    state[3] = temp;
}

static uint8_t AesXtime(uint8_t b)
{
    return (uint8_t)((b << 1) ^ (((b >> 7) & 1U) ? 0x1BU : 0x00U));
}

static void AesMixColumns(uint8_t state[16])
{
    uint32_t c;
    for (c = 0U; c < 4U; ++c)
    {
        uint32_t idx = c * 4U;
        uint8_t a0 = state[idx + 0U];
        uint8_t a1 = state[idx + 1U];
        uint8_t a2 = state[idx + 2U];
        uint8_t a3 = state[idx + 3U];

        uint8_t t = a0 ^ a1 ^ a2 ^ a3;
        uint8_t u = a0;

        state[idx + 0U] ^= t ^ AesXtime((uint8_t)(a0 ^ a1));
        state[idx + 1U] ^= t ^ AesXtime((uint8_t)(a1 ^ a2));
        state[idx + 2U] ^= t ^ AesXtime((uint8_t)(a2 ^ a3));
        state[idx + 3U] ^= t ^ AesXtime((uint8_t)(a3 ^ u));
    }
}

static void AesAddRoundKey(uint8_t state[16], const uint8_t rk[16])
{
    uint32_t i;
    for (i = 0U; i < 16U; ++i)
    {
        state[i] ^= rk[i];
    }
}

void SecOcAesBlock_Task5ms(void)
{
    uint32_t round;
    AesAddRoundKey(s_aes_state, s_aes_round_key);

    for (round = 1U; round < 10U; ++round)
    {
        AesSubBytes(s_aes_state);
        AesShiftRows(s_aes_state);
        AesMixColumns(s_aes_state);
        AesAddRoundKey(s_aes_state, s_aes_round_key);
    }

    /* Final round (no MixColumns) */
    AesSubBytes(s_aes_state);
    AesShiftRows(s_aes_state);
    AesAddRoundKey(s_aes_state, s_aes_round_key);

    g_bench_sink8 = s_aes_state[0] ^ s_aes_state[15];
}

/* ========================================================================= */
/* 4. POWERTRAIN KNOCK FFT (16-Point Radix-2 DIT FFT)                         */
/* ========================================================================= */
#define FFT_POINTS 16U

/* Q14 Twiddle factors: cos(2*pi*k/16), -sin(2*pi*k/16) for k=0..7 */
static const int16_t s_twiddle_cos[8] = {
    16384, 15137, 11585, 6270, 0, -6270, -11585, -15137
};
static const int16_t s_twiddle_sin[8] = {
    0, -6270, -11585, -15137, -16384, -15137, -11585, -6270
};

static int16_t s_fft_real[FFT_POINTS];
static int16_t s_fft_imag[FFT_POINTS];
static uint32_t s_fft_power[8];

static void FftBitReverse(int16_t real[FFT_POINTS], int16_t imag[FFT_POINTS])
{
    uint32_t i, j = 0U;
    for (i = 0U; i < FFT_POINTS - 1U; ++i)
    {
        if (i < j)
        {
            int16_t tr = real[i]; real[i] = real[j]; real[j] = tr;
            int16_t ti = imag[i]; imag[i] = imag[j]; imag[j] = ti;
        }
        uint32_t k = FFT_POINTS >> 1U;
        while (k <= j)
        {
            j -= k;
            k >>= 1U;
        }
        j += k;
    }
}

static void FftButterflyStages(int16_t real[FFT_POINTS], int16_t imag[FFT_POINTS])
{
    uint32_t stage;
    uint32_t num_bf = 1U;
    uint32_t step = 2U;

    for (stage = 0U; stage < 4U; ++stage) /* log2(16) = 4 */
    {
        uint32_t group;
        for (group = 0U; group < FFT_POINTS; group += step)
        {
            uint32_t pair;
            for (pair = 0U; pair < num_bf; ++pair)
            {
                uint32_t idx_a = group + pair;
                uint32_t idx_b = idx_a + num_bf;
                uint32_t twiddle_idx = (pair * 8U) / num_bf;

                int16_t wr = s_twiddle_cos[twiddle_idx];
                int16_t wi = s_twiddle_sin[twiddle_idx];

                /* Complex multiplication: temp = W * data[idx_b] */
                int32_t br = real[idx_b];
                int32_t bi = imag[idx_b];
                int16_t tr = (int16_t)((br * wr - bi * wi) >> 14);
                int16_t ti = (int16_t)((br * wi + bi * wr) >> 14);

                real[idx_b] = real[idx_a] - tr;
                imag[idx_b] = imag[idx_a] - ti;
                real[idx_a] = real[idx_a] + tr;
                imag[idx_a] = imag[idx_a] + ti;
            }
        }
        num_bf <<= 1U;
        step <<= 1U;
    }
}

static void FftPowerSpectrum(const int16_t real[FFT_POINTS], const int16_t imag[FFT_POINTS], uint32_t power[8])
{
    uint32_t i;
    for (i = 0U; i < 8U; ++i)
    {
        int32_t r = real[i];
        int32_t im = imag[i];
        power[i] = (uint32_t)(r * r + im * im);
    }
}

void PowertrainKnockFft_Task20ms(void)
{
    FftBitReverse(s_fft_real, s_fft_imag);
    FftButterflyStages(s_fft_real, s_fft_imag);
    FftPowerSpectrum(s_fft_real, s_fft_imag, s_fft_power);
    g_bench_sink32 = s_fft_power[0] + s_fft_power[1] + s_fft_power[2] + s_fft_power[3];
}

/* ========================================================================= */
/* 5. ADAPTIVE CRUISE CONTROL (ISO 15622 ACC FSM + PID + Anti-Windup)         */
/* ========================================================================= */
typedef enum
{
    ACC_STANDBY = 0,
    ACC_SPEED_CONTROL = 1,
    ACC_DISTANCE_CONTROL = 2,
    ACC_EMERGENCY_BRAKE = 3
} AccState;

static AccState s_acc_state;
static int32_t  s_acc_ego_speed;     /* mm/s */
static int32_t  s_acc_set_speed;     /* mm/s */
static int32_t  s_acc_target_dist;   /* mm */
static int32_t  s_acc_target_relspd; /* mm/s */
static int32_t  s_acc_integral_err;
static int32_t  s_acc_prev_err;
static int32_t  s_acc_prev_cmd;

static AccState AccStateTransition(AccState current, int32_t dist, int32_t ego_spd)
{
    if (dist > 0 && dist < 5000) /* Less than 5m -> Emergency */
    {
        return ACC_EMERGENCY_BRAKE;
    }

    switch (current)
    {
        case ACC_STANDBY:
            if (ego_spd > 2000) { return ACC_SPEED_CONTROL; }
            break;
        case ACC_SPEED_CONTROL:
            if (dist > 0 && dist < 40000) { return ACC_DISTANCE_CONTROL; }
            break;
        case ACC_DISTANCE_CONTROL:
            if (dist <= 0 || dist > 50000) { return ACC_SPEED_CONTROL; }
            break;
        case ACC_EMERGENCY_BRAKE:
            if (dist > 15000 || dist <= 0) { return ACC_STANDBY; }
            break;
        default:
            return ACC_STANDBY;
    }
    return current;
}

static int32_t AccPidCompute(int32_t error, int32_t *integral, int32_t *prev_err)
{
    const int32_t Kp = 120;
    const int32_t Ki = 15;
    const int32_t Kd = 40;

    int32_t p_term = (Kp * error) / 100;

    /* Integral with anti-windup clamping */
    *integral += error;
    if (*integral > 10000) { *integral = 10000; }
    else if (*integral < -10000) { *integral = -10000; }
    int32_t i_term = (Ki * (*integral)) / 100;

    /* Derivative term */
    int32_t d_term = (Kd * (error - *prev_err)) / 100;
    *prev_err = error;

    int32_t output = p_term + i_term + d_term;
    if (output > 3000) { output = 3000; }       /* max accel: 3.0 m/s^2 */
    else if (output < -5000) { output = -5000; } /* max brake: -5.0 m/s^2 */
    return output;
}

static int32_t AccSlewRateLimit(int32_t desired_cmd, int32_t prev_cmd, int32_t max_rate)
{
    int32_t delta = desired_cmd - prev_cmd;
    if (delta > max_rate)
    {
        return prev_cmd + max_rate;
    }
    else if (delta < -max_rate)
    {
        return prev_cmd - max_rate;
    }
    return desired_cmd;
}

void AccAdaptiveControl_Task20ms(void)
{
    s_acc_state = AccStateTransition(s_acc_state, s_acc_target_dist, s_acc_ego_speed);

    int32_t raw_cmd = 0;
    if (s_acc_state == ACC_EMERGENCY_BRAKE)
    {
        raw_cmd = -5000; /* Full emergency decel */
    }
    else if (s_acc_state == ACC_DISTANCE_CONTROL)
    {
        /* Desired distance = time_gap * ego_speed + d0 (time_gap = 1.5s -> 1500ms) */
        int32_t des_dist = 5000 + (s_acc_ego_speed * 15) / 10;
        int32_t dist_err = s_acc_target_dist - des_dist;
        raw_cmd = AccPidCompute(dist_err, &s_acc_integral_err, &s_acc_prev_err);
    }
    else if (s_acc_state == ACC_SPEED_CONTROL)
    {
        int32_t spd_err = s_acc_set_speed - s_acc_ego_speed;
        raw_cmd = AccPidCompute(spd_err, &s_acc_integral_err, &s_acc_prev_err);
    }
    else
    {
        raw_cmd = 0; /* Standby / coast */
    }

    int32_t limited_cmd = AccSlewRateLimit(raw_cmd, s_acc_prev_cmd, 400); /* max jerk rate */
    s_acc_prev_cmd = limited_cmd;
    g_bench_sink32 = (uint32_t)limited_cmd ^ (uint32_t)s_acc_state;
}

/* ========================================================================= */
/* 6. MOTOR FIELD ORIENTED CONTROL (FOC - Clarke, Park, PI, InvPark, SVPWM)  */
/* ========================================================================= */
#define FOC_SCALE_Q15       32768
#define FOC_INV_SQRT3_Q15   18892 /* 1 / sqrt(3) * 32768 */
#define FOC_SQRT3_Q15       56756 /* sqrt(3) * 32768 */
#define FOC_V_MAX_Q15       30000 /* Voltage limit */

static int32_t s_foc_ia;          /* Phase A current (Q15) */
static int32_t s_foc_ib;          /* Phase B current (Q15) */
static int32_t s_foc_id_ref;      /* Direct axis reference current */
static int32_t s_foc_iq_ref;      /* Quadrature axis reference current */
static int32_t s_foc_id_integ;    /* D-axis integrator */
static int32_t s_foc_iq_integ;    /* Q-axis integrator */
static int32_t s_foc_sector;      /* Output SVPWM sector (1..6) */

/* Forward Clarke Transformation: (ia, ib) -> (ialpha, ibeta) */
static void FocClarkeTransform(int32_t ia, int32_t ib, int32_t *ialpha, int32_t *ibeta)
{
    *ialpha = ia;
    int32_t sum = ia + 2 * ib;
    *ibeta = (sum * FOC_INV_SQRT3_Q15) / FOC_SCALE_Q15;
}

/* Forward Park Transformation: (ialpha, ibeta, sin, cos) -> (id, iq) */
static void FocParkTransform(int32_t ialpha, int32_t ibeta, int32_t sin_t, int32_t cos_t, int32_t *id, int32_t *iq)
{
    *id = (ialpha * cos_t + ibeta * sin_t) / FOC_SCALE_Q15;
    *iq = (-ialpha * sin_t + ibeta * cos_t) / FOC_SCALE_Q15;
}

/* PI Current Controller with Anti-Windup Saturation */
static int32_t FocPiController(int32_t err, int32_t *integral, int32_t kp, int32_t ki)
{
    *integral += (err * ki) / FOC_SCALE_Q15;
    if (*integral > FOC_V_MAX_Q15)
    {
        *integral = FOC_V_MAX_Q15;
    }
    else if (*integral < -FOC_V_MAX_Q15)
    {
        *integral = -FOC_V_MAX_Q15;
    }

    int32_t out = (err * kp) / FOC_SCALE_Q15 + *integral;
    if (out > FOC_V_MAX_Q15)
    {
        out = FOC_V_MAX_Q15;
    }
    else if (out < -FOC_V_MAX_Q15)
    {
        out = -FOC_V_MAX_Q15;
    }
    return out;
}

/* Inverse Park Transformation: (vd, vq, sin, cos) -> (valpha, vbeta) */
static void FocInvParkTransform(int32_t vd, int32_t vq, int32_t sin_t, int32_t cos_t, int32_t *valpha, int32_t *vbeta)
{
    *valpha = (vd * cos_t - vq * sin_t) / FOC_SCALE_Q15;
    *vbeta  = (vd * sin_t + vq * cos_t) / FOC_SCALE_Q15;
}

/* Space Vector PWM Sector Identification */
static int32_t FocSvpwmSector(int32_t valpha, int32_t vbeta)
{
    int32_t v_ref1 = vbeta;
    int32_t v_ref2 = (-vbeta + ((valpha * FOC_SQRT3_Q15) / FOC_SCALE_Q15)) / 2;
    int32_t v_ref3 = (-vbeta - ((valpha * FOC_SQRT3_Q15) / FOC_SCALE_Q15)) / 2;

    int32_t a = (v_ref1 > 0) ? 1 : 0;
    int32_t b = (v_ref2 > 0) ? 2 : 0;
    int32_t c = (v_ref3 > 0) ? 4 : 0;

    return a + b + c;
}

void MotorFoc_CurrentLoop_Task1ms(void)
{
    int32_t ialpha, ibeta;
    int32_t id, iq;
    int32_t vd, vq;
    int32_t valpha, vbeta;

    int32_t sin_t = 19260; /* ~0.5878 in Q15 */
    int32_t cos_t = 26509; /* ~0.8090 in Q15 */

    FocClarkeTransform(s_foc_ia, s_foc_ib, &ialpha, &ibeta);
    FocParkTransform(ialpha, ibeta, sin_t, cos_t, &id, &iq);

    int32_t id_err = s_foc_id_ref - id;
    int32_t iq_err = s_foc_iq_ref - iq;

    vd = FocPiController(id_err, &s_foc_id_integ, 15000, 3000);
    vq = FocPiController(iq_err, &s_foc_iq_integ, 15000, 3000);

    FocInvParkTransform(vd, vq, sin_t, cos_t, &valpha, &vbeta);

    s_foc_sector = FocSvpwmSector(valpha, vbeta);
    g_bench_sink32 = (uint32_t)(valpha ^ vbeta ^ s_foc_sector);
}

/* ========================================================================= */
/* INITIALIZATION ROUTINE                                                    */
/* ========================================================================= */
void LiteratureHardBenchmarks_Initialize(uint32_t task_id)
{
    uint32_t i;
    switch (task_id)
    {
        case 0U: /* AdasKalmanFilter_Task10ms */
            s_kf_x[0] = 100 * KF_SCALE;
            s_kf_x[1] = 15 * KF_SCALE;
            s_kf_P[0][0] = 10 * KF_SCALE; s_kf_P[0][1] = 0;
            s_kf_P[1][0] = 0;             s_kf_P[1][1] = 10 * KF_SCALE;
            s_kf_A[0][0] = 1 * KF_SCALE;  s_kf_A[0][1] = (KF_SCALE * 1) / 100; /* dt = 10ms */
            s_kf_A[1][0] = 0;             s_kf_A[1][1] = 1 * KF_SCALE;
            s_kf_Q[0][0] = 2 * KF_SCALE;  s_kf_Q[0][1] = 0;
            s_kf_Q[1][0] = 0;             s_kf_Q[1][1] = 2 * KF_SCALE;
            s_kf_meas_pos = 102 * KF_SCALE;
            break;

        case 1U: /* CordicResolver_Task1ms */
            s_cordic_target_angle = 12500; /* ~43.9 degrees in Q14 (16384 rad) */
            break;

        case 2U: /* SecOcAesBlock_Task5ms */
            for (i = 0U; i < 16U; ++i)
            {
                s_aes_state[i] = (uint8_t)(0x30U + i * 7U);
            }
            break;

        case 3U: /* PowertrainKnockFft_Task20ms */
            for (i = 0U; i < FFT_POINTS; ++i)
            {
                s_fft_real[i] = (int16_t)(i * 210 - 1500);
                s_fft_imag[i] = 0;
            }
            break;

        case 4U: /* AccAdaptiveControl_Task20ms */
            s_acc_state = ACC_DISTANCE_CONTROL;
            s_acc_ego_speed = 25000;     /* 25 m/s (~90 km/h) */
            s_acc_set_speed = 28000;     /* 28 m/s (~100 km/h) */
            s_acc_target_dist = 35000;   /* 35m */
            s_acc_target_relspd = -1000; /* closing in at 1 m/s */
            s_acc_integral_err = 500;
            s_acc_prev_err = 450;
            s_acc_prev_cmd = 100;
            break;

        case 5U: /* MotorFoc_CurrentLoop_Task1ms */
            s_foc_ia = 8000;      /* Phase A current: ~0.244 in Q15 */
            s_foc_ib = -4000;     /* Phase B current: ~-0.122 in Q15 */
            s_foc_id_ref = 0;     /* Id ref = 0 for PMSM MTPA */
            s_foc_iq_ref = 10000; /* Iq ref = 10000 in Q15 */
            s_foc_id_integ = 500;
            s_foc_iq_integ = 1200;
            s_foc_sector = 1;
            break;

        default:
            break;
    }
}
