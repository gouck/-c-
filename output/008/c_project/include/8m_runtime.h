#ifndef _8M_RUNTIME_H_
#define _8M_RUNTIME_H_

#include <stdint.h>
#include <string.h>

#define FIELD_INDEX_GET(parent, field, idx) \
    ((idx) == 0 ? (parent).field##0 : \
     (idx) == 1 ? (parent).field##1 : \
     (idx) == 2 ? (parent).field##2 : \
     (parent).field##3)

/* External placeholder functions */
static inline uint32_t hash1(uint32_t v) { return v % 512; }
#define Max(a, b) ((a) > (b) ? (a) : (b))
#define Max3(a, b, c) Max(Max(a, b), c)
/* enqueue_packet/send_packet are weak symbols in 8m_common.c — tb.c overrides them */
void enqueue_packet(void *pkt, int len);
void send_packet(void *pkt, int len);

/* Global packet buffer */
extern uint8_t PacketByte[512];

static inline uint64_t _concat_range(uint32_t s, uint32_t e) {
    uint64_t result = 0;
    for (uint32_t i = s; i <= e; i++)
        result = (result << 8) | PacketByte[i];
    return result;
}

#endif /* _8M_RUNTIME_H_ */
