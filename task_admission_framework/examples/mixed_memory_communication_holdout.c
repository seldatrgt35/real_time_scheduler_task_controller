typedef __UINT8_TYPE__ uint8_t;
typedef __UINT32_TYPE__ uint32_t;

static uint32_t g_star_holdout_signals[16U];
static uint8_t g_star_holdout_payload[16U];
static volatile uint32_t g_star_holdout_result;

void StarMixedCommunicationHoldout_Initialize(void)
{
    uint32_t index;
    for (index = 0U; index < 16U; ++index)
    {
        g_star_holdout_signals[index] = (index * 173U) + 31U;
        g_star_holdout_payload[index] = 0U;
    }
    g_star_holdout_result = 0U;
}

void StarMixedCommunicationHoldoutTask(void)
{
    uint32_t index;
    uint32_t checksum = 0U;
    uint32_t state = 0U;

    for (index = 0U; index < 12U; ++index)
    {
        g_star_holdout_payload[index] =
            (uint8_t)(g_star_holdout_signals[index] & 0xFFU);
    }
    for (index = 0U; index < 12U; ++index)
    {
        checksum ^= (uint32_t)g_star_holdout_payload[index] & 0xFFU;
    }
    for (index = 0U; index < 20U; ++index)
    {
        switch (index & 3U)
        {
            case 0U: state += 1U; break;
            case 1U: state ^= 2U; break;
            case 2U: state |= 4U; break;
            default: state &= 0xFFFFFFFEU; break;
        }
    }
    g_star_holdout_result = state ^ checksum;
}
