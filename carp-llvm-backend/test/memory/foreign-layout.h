#ifndef METACARP_TEST_FOREIGN_LAYOUT_H
#define METACARP_TEST_FOREIGN_LAYOUT_H
#include <stdint.h>

typedef struct {
  uint64_t first;
  uint8_t middle;
  uint64_t last;
#if FOREIGN_LAYOUT_EXTRA
  uint64_t extra;
#endif
} ForeignWide;

typedef struct __attribute__((packed)) {
  uint8_t head;
  int32_t word;
} ForeignPacked;

typedef struct {
  _Alignas(32) unsigned char bytes[33];
} ForeignAligned;

typedef struct ForeignIncomplete ForeignIncomplete;

static ForeignWide foreign_wide(void) {
  ForeignWide value = {0};
  value.first = 11;
  value.middle = 7;
  value.last = 29;
  return value;
}

static ForeignPacked foreign_packed(void) {
  ForeignPacked value = {3, 41};
  return value;
}

static ForeignAligned foreign_aligned(void) {
  ForeignAligned value = {0};
  value.bytes[0] = 17;
  value.bytes[32] = 31;
  return value;
}

static ForeignWide foreign_wide_copy(ForeignWide* value) { return *value; }
static ForeignPacked foreign_packed_copy(ForeignPacked* value) { return *value; }
static ForeignAligned foreign_aligned_copy(ForeignAligned* value) { return *value; }

static int foreign_check(ForeignWide wide, ForeignPacked packed,
                         ForeignAligned aligned) {
  return wide.first == 11 && wide.middle == 7 && wide.last == 29 &&
         packed.head == 3 && packed.word == 41 &&
         aligned.bytes[0] == 17 && aligned.bytes[32] == 31;
}
#endif
